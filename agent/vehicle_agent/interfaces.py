from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from agent.vehicle_agent.models import PositionFix, Sample


class PositionProvider(Protocol):
    def read(self) -> PositionFix | None: ...


class VehicleDataProvider(Protocol):
    def read_metrics(self) -> Mapping[str, object]: ...


class SystemHealthProvider(Protocol):
    def read_health(self) -> Mapping[str, object]: ...


class StorageQueue(Protocol):
    def enqueue(self, sample: Sample) -> None: ...

    def pending(self, limit: int) -> Sequence[Sample]: ...

    def acknowledge(self, sample_ids: Sequence[str]) -> int: ...

    def depth(self) -> int: ...


class Transport(Protocol):
    def upload(self, samples: Sequence[Sample]) -> Sequence[str]: ...


class ConfigurationProvider(Protocol):
    def fetch_config(self) -> dict[str, Any]: ...
