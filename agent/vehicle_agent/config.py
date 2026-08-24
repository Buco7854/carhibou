import json
import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


class ConfigurationError(Exception):
    pass


@dataclass(frozen=True)
class AgentConfiguration:
    version: int
    sample_seconds: int
    upload_seconds: int
    vehicle_profile: str | None

    @classmethod
    def parse(cls, data: dict[str, Any]) -> "AgentConfiguration":
        try:
            version = int(data["version"])
            sample = int(data["sampling"]["default_seconds"])
            upload = int(data["upload"]["default_seconds"])
            profile = data.get("vehicle_profile")
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigurationError("remote configuration has invalid structure") from exc
        if version < 1 or not 1 <= sample <= 86400 or not 1 <= upload <= 86400:
            raise ConfigurationError("remote configuration values are outside safe bounds")
        if profile is not None and not isinstance(profile, str):
            raise ConfigurationError("vehicle_profile must be a string or null")
        return cls(version, sample, upload, profile)

    def as_server_format(self) -> dict[str, object]:
        return {
            "version": self.version,
            "sampling": {"default_seconds": self.sample_seconds},
            "upload": {"default_seconds": self.upload_seconds},
            "vehicle_profile": self.vehicle_profile,
        }


class ConfigurationStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> AgentConfiguration:
        try:
            return AgentConfiguration.parse(json.loads(self.path.read_text()))
        except (OSError, json.JSONDecodeError, ConfigurationError) as exc:
            raise ConfigurationError(f"cannot load last-known-good configuration: {exc}") from exc

    def install_if_newer(self, data: dict[str, Any]) -> AgentConfiguration:
        candidate = AgentConfiguration.parse(data)
        try:
            current = self.load()
        except ConfigurationError:
            current = None
        if current and candidate.version < current.version:
            raise ConfigurationError("refusing configuration version rollback")
        if current and candidate.version == current.version:
            return current
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", dir=self.path.parent, delete=False) as temporary:
            json.dump(candidate.as_server_format(), temporary, indent=2)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.chmod(temporary_path, 0o600)
        temporary_path.replace(self.path)
        return candidate
