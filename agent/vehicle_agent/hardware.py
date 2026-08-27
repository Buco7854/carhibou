import glob
import json
import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


class HardwareConfigurationError(Exception):
    pass


AUTO = "auto"
OFF = "off"


def _parse_selection(value: object, source: str) -> str:
    if not isinstance(value, str) or not value:
        raise HardwareConfigurationError(f"{source} selection must be auto, off, or a device path")
    if value in {AUTO, OFF}:
        return value
    if not value.startswith("/dev/"):
        raise HardwareConfigurationError(f"{source} device must be an absolute /dev path")
    return value


@dataclass(frozen=True)
class HardwareConfiguration:
    gps: str = AUTO
    obd: str = AUTO

    @classmethod
    def parse(cls, data: dict[str, Any]) -> "HardwareConfiguration":
        return cls(
            gps=_parse_selection(data.get("gps", AUTO), "GPS"),
            obd=_parse_selection(data.get("obd", AUTO), "OBD"),
        )

    def as_dict(self) -> dict[str, str]:
        return {"gps": self.gps, "obd": self.obd}


class HardwareConfigurationStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> HardwareConfiguration:
        if not self.path.exists():
            return HardwareConfiguration()
        try:
            data = json.loads(self.path.read_text())
            if not isinstance(data, dict):
                raise HardwareConfigurationError("hardware configuration must be an object")
            return HardwareConfiguration.parse(data)
        except (OSError, json.JSONDecodeError, HardwareConfigurationError) as exc:
            raise HardwareConfigurationError(f"cannot load hardware configuration: {exc}") from exc

    def save(self, configuration: HardwareConfiguration) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", dir=self.path.parent, delete=False) as temporary:
            json.dump(configuration.as_dict(), temporary, indent=2)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        # Device paths are not secrets. World-readable mode lets the unprivileged
        # service consume a file written by an administrator through sudo.
        os.chmod(temporary_path, 0o644)
        temporary_path.replace(self.path)


def serial_candidates() -> list[str]:
    """Return stable serial paths first, followed by conventional Linux fallbacks."""
    paths = glob.glob("/dev/serial/by-id/*") + glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
    return list(dict.fromkeys(sorted(paths, key=lambda path: ("/by-id/" not in path, path))))


def gps_candidates() -> list[str]:
    candidates = serial_candidates()
    likely = [path for path in candidates if "simtech" in path.lower()]
    fallback = [path for path in candidates if path == "/dev/ttyUSB1"]
    generic = [
        path
        for path in candidates
        if path not in likely
        and path not in fallback
        and "obdlink" not in path.lower()
        and "ftdi" not in path.lower()
    ]
    return likely + fallback + generic


def obd_candidates() -> list[str]:
    candidates = serial_candidates()
    likely = [path for path in candidates if "obdlink" in path.lower() or "ftdi" in path.lower()]
    generic = [path for path in candidates if path not in likely and "simtech" not in path.lower()]
    return likely + generic


def resolve_selection(selection: str, discovered: list[str]) -> str | None:
    if selection == OFF:
        return None
    if selection == AUTO:
        return discovered[0] if discovered else None
    return selection
