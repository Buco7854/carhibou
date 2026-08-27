import argparse
import json
from pathlib import Path

import pytest

from agent.vehicle_agent.cli import build_parser, command_devices_set
from agent.vehicle_agent.hardware import (
    HardwareConfiguration,
    HardwareConfigurationError,
    HardwareConfigurationStore,
    gps_candidates,
    obd_candidates,
    resolve_selection,
    serial_candidates,
)


def test_hardware_configuration_defaults_and_persists(tmp_path: Path) -> None:
    store = HardwareConfigurationStore(tmp_path / "hardware.json")
    assert store.load() == HardwareConfiguration(gps="auto", obd="auto")

    store.save(HardwareConfiguration(gps="off", obd="/dev/serial/by-id/obdlink"))

    assert store.load() == HardwareConfiguration(gps="off", obd="/dev/serial/by-id/obdlink")
    assert json.loads((tmp_path / "hardware.json").read_text())["gps"] == "off"


def test_hardware_configuration_rejects_non_device_paths() -> None:
    with pytest.raises(HardwareConfigurationError, match="absolute /dev path"):
        HardwareConfiguration.parse({"gps": "ttyUSB1", "obd": "auto"})


def test_candidate_discovery_prefers_stable_and_source_specific_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discovered = {
        "/dev/serial/by-id/*": [
            "/dev/serial/by-id/usb-SimTech_modem",
            "/dev/serial/by-id/usb-OBDLink_SX",
        ],
        "/dev/ttyUSB*": ["/dev/ttyUSB0", "/dev/ttyUSB1"],
        "/dev/ttyACM*": [],
    }
    monkeypatch.setattr(
        "agent.vehicle_agent.hardware.glob.glob", lambda pattern: discovered[pattern]
    )

    assert serial_candidates()[0].startswith("/dev/serial/by-id/")
    assert gps_candidates()[0] == "/dev/serial/by-id/usb-SimTech_modem"
    assert obd_candidates()[0] == "/dev/serial/by-id/usb-OBDLink_SX"
    assert resolve_selection("auto", obd_candidates()) == "/dev/serial/by-id/usb-OBDLink_SX"
    assert resolve_selection("off", obd_candidates()) is None


def test_devices_set_saves_auto_or_off_without_inline_runtime_flags(tmp_path: Path) -> None:
    args = argparse.Namespace(config_dir=tmp_path, gps="off", obd="auto")

    assert command_devices_set(args) == 0
    assert HardwareConfigurationStore(tmp_path / "hardware.json").load() == HardwareConfiguration(
        gps="off", obd="auto"
    )
    parsed = build_parser().parse_args(["--config-dir", str(tmp_path), "devices"])
    assert parsed.handler.__name__ == "command_devices"
    uninstall = build_parser().parse_args(["uninstall", "--yes"])
    assert uninstall.handler.__name__ == "command_uninstall"
    assert uninstall.yes is True
