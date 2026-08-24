import argparse
import json
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
from agent.vehicle_agent.interfaces import VehicleDataProvider
from agent.vehicle_agent.profile_decoder import VehicleProfileDecoder
from agent.vehicle_agent.providers.nmea import (
    NullPositionProvider,
    SIM7600NMEAProvider,
    discover_sim7600_nmea,
)
from agent.vehicle_agent.providers.obdlink import OBDLinkSXAdapter, discover_obdlink
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

DEFAULT_DATA = Path("/var/lib/vehinode-agent")
DEFAULT_CONFIG = Path("/etc/vehinode-agent")


def _credentials(path: Path) -> dict[str, str]:
    try:
        return {key: str(value) for key, value in json.loads(path.read_text()).items()}
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot read credentials: {exc}") from exc


def command_status(args: argparse.Namespace) -> int:
    queue = SQLiteQueue(args.data_dir / "queue.sqlite3")
    credentials_present = (args.config_dir / "credentials.json").is_file()
    print(f"VehiNode agent {__version__}")
    print(f"Credentials: {'installed' if credentials_present else 'missing'}")
    print(f"Queued telemetry: {queue.depth()}")
    return 0 if credentials_present else 1


def command_doctor(args: argparse.Namespace) -> int:
    checks = {
        "platform": platform.platform(),
        "credentials": (args.config_dir / "credentials.json").is_file(),
        "queue_writable": args.data_dir.exists() and args.data_dir.is_dir(),
        "gps_device": str(discover_sim7600_nmea() or "not detected"),
        "obd_devices": discover_obdlink(),
    }
    print(json.dumps(checks, indent=2))
    return 0 if checks["credentials"] and checks["queue_writable"] else 1


def command_logs(_args: argparse.Namespace) -> int:
    return subprocess.call(["journalctl", "-u", "vehinode-agent", "-n", "200", "--no-pager"])


def command_config(args: argparse.Namespace) -> int:
    try:
        config = ConfigurationStore(args.config_dir / "config.json").load()
    except ConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(config.as_server_format(), indent=2))
    return 0


def command_gps(args: argparse.Namespace) -> int:
    device = args.device or discover_sim7600_nmea()
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
    devices = [args.device] if args.device else discover_obdlink()
    if not devices:
        print("No OBDLink serial device detected", file=sys.stderr)
        return 1
    adapter = OBDLinkSXAdapter(devices[0])
    try:
        adapter.connect()
        details: dict[str, object] = {"device": devices[0], **adapter.identity()}
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
    devices = [args.device] if args.device else discover_obdlink()
    if not devices:
        print("No OBDLink serial device detected", file=sys.stderr)
        return 1
    adapter = OBDLinkSXAdapter(devices[0])
    try:
        adapter.connect()
        metadata = {
            "adapter": adapter.identity(),
            "vehicle_profile": args.profile,
            "device": devices[0],
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
    print(f"Enrolled device {response['device_id']}")
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
    gps_device = args.gps_device or discover_sim7600_nmea()
    position = SIM7600NMEAProvider(str(gps_device)) if gps_device else NullPositionProvider()
    obd_devices = [args.obd_device] if args.obd_device else discover_obdlink()
    vehicle: VehicleDataProvider = StaticVehicleProvider()
    if obd_devices and config.vehicle_profile:
        profile_path = Path(__file__).parents[1] / "profiles" / f"{config.vehicle_profile}.yaml"
        if profile_path.is_file():
            vehicle = RawCANProfileProvider(
                OBDLinkSXAdapter(obd_devices[0]), VehicleProfileDecoder.from_path(profile_path)
            )
        else:
            print(f"Vehicle profile is not installed: {config.vehicle_profile}", file=sys.stderr)
            return 1
    elif obd_devices:
        vehicle = StandardOBDProvider(OBDLinkSXAdapter(obd_devices[0]))
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
                if preview.vehicle_profile:
                    preview_path = (
                        Path(__file__).parents[1] / "profiles" / f"{preview.vehicle_profile}.yaml"
                    )
                    if not preview_path.is_file():
                        raise ConfigurationError(
                            f"vehicle profile is not installed: {preview.vehicle_profile}"
                        )
                candidate = config_store.install_if_newer(remote_config)
                if candidate.vehicle_profile != config.vehicle_profile:
                    old_adapter = getattr(runtime.vehicle, "adapter", None)
                    if old_adapter:
                        old_adapter.close()
                    if obd_devices and candidate.vehicle_profile:
                        candidate_path = (
                            Path(__file__).parents[1]
                            / "profiles"
                            / f"{candidate.vehicle_profile}.yaml"
                        )
                        if not candidate_path.is_file():
                            raise ConfigurationError(
                                f"vehicle profile is not installed: {candidate.vehicle_profile}"
                            )
                        runtime.vehicle = RawCANProfileProvider(
                            OBDLinkSXAdapter(obd_devices[0]),
                            VehicleProfileDecoder.from_path(candidate_path),
                        )
                    elif obd_devices:
                        runtime.vehicle = StandardOBDProvider(OBDLinkSXAdapter(obd_devices[0]))
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
    try:
        return subprocess.call(
            [
                "sudo",
                "sh",
                path,
                "--server",
                credentials["server_url"],
                "--version",
                args.version,
                "--update-only",
            ]
        )
    finally:
        Path(path).unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vehinode-agent")
    parser.add_argument("--config-dir", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status").set_defaults(handler=command_status)
    sub.add_parser("doctor").set_defaults(handler=command_doctor)
    sub.add_parser("logs").set_defaults(handler=command_logs)
    sub.add_parser("config").set_defaults(handler=command_config)
    update = sub.add_parser("update")
    update.add_argument("--version", required=True)
    update.set_defaults(handler=command_update)
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
