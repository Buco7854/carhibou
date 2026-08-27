import argparse
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.request import urlopen
from uuid import uuid4

from agent.vehicle_agent import __version__
from agent.vehicle_agent.capture import CANRecorder, replay_capture
from agent.vehicle_agent.config import AgentConfiguration, ConfigurationError, ConfigurationStore
from agent.vehicle_agent.enrollment import enroll, store_credentials
from agent.vehicle_agent.hardware import (
    AUTO,
    OFF,
    HardwareConfiguration,
    HardwareConfigurationError,
    HardwareConfigurationStore,
    gps_candidates,
    obd_candidates,
    resolve_selection,
)
from agent.vehicle_agent.interfaces import VehicleDataProvider
from agent.vehicle_agent.profile_decoder import VehicleProfileDecoder
from agent.vehicle_agent.providers.nmea import (
    NullPositionProvider,
    SIM7600NMEAProvider,
)
from agent.vehicle_agent.providers.obdlink import OBDLinkSXAdapter
from agent.vehicle_agent.providers.raw_can import RawCANProfileProvider
from agent.vehicle_agent.providers.standard_obd import (
    StandardOBDProvider,
    parse_dtc_response,
    parse_vin_response,
)
from agent.vehicle_agent.queue import SQLiteQueue
from agent.vehicle_agent.runtime import AgentRuntime, StaticVehicleProvider
from agent.vehicle_agent.simulator.journey import SimulatedCZeroJourney
from agent.vehicle_agent.system_health import LinuxSystemHealthProvider
from agent.vehicle_agent.transport import HTTPSBatchTransport, TransportError

DEFAULT_DATA = Path("/var/lib/carhibou-agent")
DEFAULT_CONFIG = Path("/etc/carhibou-agent")


def _profile_decoder(config: AgentConfiguration) -> VehicleProfileDecoder | None:
    if not config.vehicle_profile:
        return None
    if config.vehicle_profile_definition:
        return VehicleProfileDecoder(config.vehicle_profile_definition)
    profile_path = Path(__file__).parents[1] / "profiles" / f"{config.vehicle_profile}.yaml"
    if not profile_path.is_file():
        raise ConfigurationError(f"vehicle profile is not installed: {config.vehicle_profile}")
    return VehicleProfileDecoder.from_path(profile_path)


def _credentials(path: Path) -> dict[str, str]:
    try:
        return {key: str(value) for key, value in json.loads(path.read_text()).items()}
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot read credentials: {exc}") from exc


def command_status(args: argparse.Namespace) -> int:
    queue = SQLiteQueue(args.data_dir / "queue.sqlite3")
    credentials_present = (args.config_dir / "credentials.json").is_file()
    print(f"Carhibou agent {__version__}")
    print(f"Credentials: {'installed' if credentials_present else 'missing'}")
    print(f"Queued telemetry: {queue.depth()}")
    return 0 if credentials_present else 1


def _hardware(args: argparse.Namespace) -> HardwareConfiguration:
    return HardwareConfigurationStore(args.config_dir / "hardware.json").load()


def _selected_devices(args: argparse.Namespace) -> tuple[str | None, str | None]:
    hardware = _hardware(args)
    return (
        resolve_selection(hardware.gps, gps_candidates()),
        resolve_selection(hardware.obd, obd_candidates()),
    )


def command_devices(args: argparse.Namespace) -> int:
    try:
        hardware = _hardware(args)
    except HardwareConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    gps = gps_candidates()
    obd = obd_candidates()
    print(
        json.dumps(
            {
                "selection": hardware.as_dict(),
                "resolved": {
                    "gps": resolve_selection(hardware.gps, gps),
                    "obd": resolve_selection(hardware.obd, obd),
                },
                "candidates": {"gps": gps, "obd": obd},
            },
            indent=2,
        )
    )
    return 0


def command_devices_set(args: argparse.Namespace) -> int:
    if args.gps is None and args.obd is None:
        print("Choose --gps and/or --obd (auto, off, or an absolute /dev path)", file=sys.stderr)
        return 2
    try:
        current = _hardware(args)
        candidate = HardwareConfiguration.parse(
            {
                "gps": args.gps if args.gps is not None else current.gps,
                "obd": args.obd if args.obd is not None else current.obd,
            }
        )
    except HardwareConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    for source, selection in candidate.as_dict().items():
        if selection not in {AUTO, OFF} and not Path(selection).exists():
            print(f"{source.upper()} device does not exist: {selection}", file=sys.stderr)
            return 2
    HardwareConfigurationStore(args.config_dir / "hardware.json").save(candidate)
    print(json.dumps(candidate.as_dict(), indent=2))
    print("Saved. Restart the service with: sudo systemctl restart carhibou-agent")
    return 0


def command_doctor(args: argparse.Namespace) -> int:
    try:
        hardware = _hardware(args)
        gps_device, obd_device = _selected_devices(args)
        hardware_error = None
    except HardwareConfigurationError as exc:
        hardware = None
        gps_device = None
        obd_device = None
        hardware_error = str(exc)
    checks = {
        "platform": platform.platform(),
        "credentials": (args.config_dir / "credentials.json").is_file(),
        "queue_writable": args.data_dir.exists() and args.data_dir.is_dir(),
        "hardware_selection": hardware.as_dict() if hardware else None,
        "hardware_error": hardware_error,
        "gps_device": gps_device,
        "obd_device": obd_device,
        "gps_candidates": gps_candidates(),
        "obd_candidates": obd_candidates(),
    }
    print(json.dumps(checks, indent=2))
    return 0 if checks["credentials"] and checks["queue_writable"] and not hardware_error else 1


def command_logs(_args: argparse.Namespace) -> int:
    return subprocess.call(["journalctl", "-u", "carhibou-agent", "-n", "200", "--no-pager"])


def command_config(args: argparse.Namespace) -> int:
    try:
        config = ConfigurationStore(args.config_dir / "config.json").load()
    except ConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(config.as_server_format(), indent=2))
    return 0


def command_gps(args: argparse.Namespace) -> int:
    try:
        selected, _ = _selected_devices(args)
    except HardwareConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    device = args.device or selected
    if not device:
        print("No SIM7600 NMEA serial device detected", file=sys.stderr)
        return 1
    provider = SIM7600NMEAProvider(str(device))
    deadline = time.monotonic() + args.seconds
    while time.monotonic() < deadline:
        fix = provider.read()
        if fix:
            print(json.dumps({**fix.as_telemetry(), "recorded_at": str(fix.recorded_at)}))
    return 0


def command_obd(args: argparse.Namespace) -> int:
    try:
        _, selected = _selected_devices(args)
    except HardwareConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    device = args.device or selected
    if not device:
        print("No OBDLink serial device detected", file=sys.stderr)
        return 1
    adapter = OBDLinkSXAdapter(device)
    try:
        adapter.connect()
        details: dict[str, object] = {"device": device, **adapter.identity()}
        try:
            details["vin"] = parse_vin_response(adapter.command("0902"))
        except Exception:  # unsupported services are normal across vehicles
            details["vin"] = None
        try:
            details["dtcs"] = parse_dtc_response(adapter.command("03"))
        except Exception:
            details["dtcs"] = []
        print(json.dumps(details, indent=2))
    finally:
        adapter.close()
    return 0


def command_record(args: argparse.Namespace) -> int:
    try:
        _, selected = _selected_devices(args)
    except HardwareConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    device = args.device or selected
    if not device:
        print("No OBDLink serial device detected", file=sys.stderr)
        return 1
    adapter = OBDLinkSXAdapter(device)
    try:
        adapter.connect()
        metadata = {
            "adapter": adapter.identity(),
            "vehicle_profile": args.profile,
            "device": device,
        }
        with args.output.open("w") as output:
            recorder = CANRecorder(output, metadata)
            for frame in adapter.monitor(args.seconds):
                recorder.write(frame)
    finally:
        adapter.close()
    print(f"Capture written to {args.output}")
    return 0


def command_replay(args: argparse.Namespace) -> int:
    decoder = VehicleProfileDecoder.from_path(args.profile) if args.profile else None
    metrics: dict[str, object] = {}
    count = 0
    for metadata, frame in replay_capture(args.capture):
        count += 1
        row: dict[str, object] = {**frame.as_dict(), "metadata": metadata}
        if decoder:
            values = decoder.decode(frame, metrics)
            metrics.update({signal.name: signal.value for signal in values})
            row["signals"] = [signal.__dict__ for signal in values]
        print(json.dumps(row))
    print(f"Replayed {count} frames", file=sys.stderr)
    return 0


def command_enroll(args: argparse.Namespace) -> int:
    response = enroll(
        args.server,
        args.token,
        platform.node(),
        {"machine": platform.machine(), "platform": platform.platform()},
    )
    store_credentials(args.config_dir / "credentials.json", response, args.server)
    remote_config = response.get("config")
    if not isinstance(remote_config, dict):
        raise ConfigurationError("enrollment response has no valid configuration")
    ConfigurationStore(args.config_dir / "config.json").install_if_newer(remote_config)
    print(f"Enrolled agent {response['agent_id']}")
    return 0


def command_simulate(args: argparse.Namespace) -> int:
    credentials = _credentials(args.config_dir / "credentials.json")
    queue = SQLiteQueue(args.data_dir / "queue.sqlite3")
    transport = HTTPSBatchTransport(
        credentials["server_url"], credentials["credential"], args.boot_id
    )
    journey = SimulatedCZeroJourney(args.samples)
    for sample in journey:
        queue.enqueue(sample)
        if queue.depth() >= args.batch_size:
            try:
                queue.acknowledge(transport.upload(queue.pending(args.batch_size)))
            except TransportError as exc:
                print(str(exc), file=sys.stderr)
        if args.interval:
            time.sleep(args.interval)
    try:
        queue.acknowledge(transport.upload(queue.pending(500)))
    except TransportError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Journey complete; queue depth {queue.depth()}")
    return 0


def command_run(args: argparse.Namespace) -> int:
    credentials = _credentials(args.config_dir / "credentials.json")
    config_store = ConfigurationStore(args.config_dir / "config.json")
    config = config_store.load()
    queue = SQLiteQueue(args.data_dir / "queue.sqlite3")
    try:
        selected_gps, selected_obd = _selected_devices(args)
    except HardwareConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    gps_device = args.gps_device or selected_gps
    position = SIM7600NMEAProvider(str(gps_device)) if gps_device else NullPositionProvider()
    obd_device = args.obd_device or selected_obd
    if (
        gps_device
        and obd_device
        and Path(gps_device).resolve(strict=False) == Path(obd_device).resolve(strict=False)
    ):
        print("GPS and OBD cannot use the same serial device", file=sys.stderr)
        return 1
    vehicle: VehicleDataProvider = StaticVehicleProvider()
    if obd_device and config.vehicle_profile:
        try:
            decoder = _profile_decoder(config)
        except ConfigurationError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        if decoder:
            vehicle = RawCANProfileProvider(OBDLinkSXAdapter(obd_device), decoder)
    elif obd_device:
        vehicle = StandardOBDProvider(OBDLinkSXAdapter(obd_device))
    transport = HTTPSBatchTransport(
        credentials["server_url"], credentials["credential"], str(uuid4())
    )
    runtime = AgentRuntime(
        queue,
        transport,
        position,
        vehicle,
        LinuxSystemHealthProvider(queue.depth),
    )
    next_sample = 0.0
    next_upload = 0.0
    next_config_sync = 0.0
    while True:
        now = time.monotonic()
        if now >= next_config_sync:
            try:
                remote_config = transport.fetch_config()
                preview = AgentConfiguration.parse(remote_config)
                _profile_decoder(preview)
                candidate = config_store.install_if_newer(remote_config)
                if (
                    candidate.vehicle_profile != config.vehicle_profile
                    or candidate.vehicle_profile_definition != config.vehicle_profile_definition
                ):
                    old_adapter = getattr(runtime.vehicle, "adapter", None)
                    if old_adapter:
                        old_adapter.close()
                    if obd_device and candidate.vehicle_profile:
                        decoder = _profile_decoder(candidate)
                        if not decoder:
                            raise ConfigurationError("vehicle profile decoder is unavailable")
                        runtime.vehicle = RawCANProfileProvider(
                            OBDLinkSXAdapter(obd_device),
                            decoder,
                        )
                    elif obd_device:
                        runtime.vehicle = StandardOBDProvider(OBDLinkSXAdapter(obd_device))
                    else:
                        runtime.vehicle = StaticVehicleProvider()
                config = candidate
            except (ConfigurationError, TransportError, OSError) as exc:
                print(f"Configuration sync retained last-known-good: {exc}", file=sys.stderr)
            next_config_sync = now + args.config_sync_seconds
        if now >= next_sample:
            runtime.collect_once()
            next_sample = now + config.sample_seconds
        if now >= next_upload:
            try:
                runtime.upload_once()
            except TransportError as exc:
                print(str(exc), file=sys.stderr)
            next_upload = now + config.upload_seconds
        time.sleep(min(1.0, max(0.1, min(next_sample, next_upload) - time.monotonic())))


def command_update(args: argparse.Namespace) -> int:
    credentials = _credentials(args.config_dir / "credentials.json")
    installer_url = credentials["server_url"].rstrip("/") + "/install-agent"
    with urlopen(installer_url, timeout=30) as response:  # noqa: S310 - enrolled URL was validated
        installer = response.read(1_000_000)
    with NamedTemporaryFile("wb", delete=False) as temporary:
        temporary.write(installer)
        path = temporary.name
    command = [
        "sudo",
        "sh",
        path,
        "--server",
        credentials["server_url"],
        "--version",
        args.version,
        "--update-only",
    ]
    if credentials["server_url"].startswith("http://"):
        command.append("--allow-insecure-http")
    try:
        return subprocess.call(command)
    finally:
        Path(path).unlink(missing_ok=True)


def command_uninstall(args: argparse.Namespace) -> int:
    uninstaller = Path("/usr/local/bin/carhibou-agent-uninstall")
    if not uninstaller.is_file():
        print(f"Uninstaller is missing: {uninstaller}", file=sys.stderr)
        return 1
    command = [str(uninstaller)]
    if getattr(os, "geteuid", lambda: 1)() != 0:
        command.insert(0, "sudo")
    if args.yes:
        command.append("--yes")
    return subprocess.call(command)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="carhibou-agent")
    parser.add_argument("--config-dir", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status").set_defaults(handler=command_status)
    sub.add_parser("doctor").set_defaults(handler=command_doctor)
    sub.add_parser("logs").set_defaults(handler=command_logs)
    sub.add_parser("config").set_defaults(handler=command_config)
    devices = sub.add_parser("devices", help="show or save local GPS and OBD device choices")
    devices.set_defaults(handler=command_devices)
    device_actions = devices.add_subparsers(dest="device_action")
    device_set = device_actions.add_parser("set", help="persist device paths, auto, or off")
    device_set.add_argument("--gps")
    device_set.add_argument("--obd")
    device_set.set_defaults(handler=command_devices_set)
    update = sub.add_parser("update")
    update.add_argument("--version", required=True)
    update.set_defaults(handler=command_update)
    uninstall = sub.add_parser("uninstall", help="fully remove the local agent and its data")
    uninstall.add_argument("--yes", action="store_true")
    uninstall.set_defaults(handler=command_uninstall)
    gps = sub.add_parser("gps-info")
    gps.add_argument("--device")
    gps.add_argument("--seconds", type=float, default=10)
    gps.set_defaults(handler=command_gps)
    obd = sub.add_parser("obd-info")
    obd.add_argument("--device")
    obd.set_defaults(handler=command_obd)
    record = sub.add_parser("can-record")
    record.add_argument("output", type=Path)
    record.add_argument("--device")
    record.add_argument("--profile")
    record.add_argument("--seconds", type=float, default=30)
    record.set_defaults(handler=command_record)
    replay = sub.add_parser("replay-can")
    replay.add_argument("capture", type=Path)
    replay.add_argument("--profile", type=Path)
    replay.set_defaults(handler=command_replay)
    enrollment = sub.add_parser("enroll")
    enrollment.add_argument("--server", required=True)
    enrollment.add_argument("--token", required=True)
    enrollment.set_defaults(handler=command_enroll)
    simulate = sub.add_parser("simulate")
    simulate.add_argument("--samples", type=int, default=120)
    simulate.add_argument("--batch-size", type=int, default=6)
    simulate.add_argument("--interval", type=float, default=0)
    simulate.add_argument("--boot-id", required=True)
    simulate.set_defaults(handler=command_simulate)
    run = sub.add_parser("run")
    run.add_argument("--gps-device")
    run.add_argument("--obd-device")
    run.add_argument("--config-sync-seconds", type=int, default=300)
    run.set_defaults(handler=command_run)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    raise SystemExit(args.handler(args))


if __name__ == "__main__":
    main()
