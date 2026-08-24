import logging
from collections.abc import Mapping
from datetime import UTC, datetime

from agent.vehicle_agent.interfaces import (
    PositionProvider,
    StorageQueue,
    SystemHealthProvider,
    Transport,
    VehicleDataProvider,
)
from agent.vehicle_agent.models import Sample

logger = logging.getLogger(__name__)


class AgentRuntime:
    def __init__(
        self,
        queue: StorageQueue,
        transport: Transport,
        position: PositionProvider,
        vehicle: VehicleDataProvider,
        health: SystemHealthProvider,
        initial_sequence: int = 0,
    ):
        self.queue = queue
        self.transport = transport
        self.position = position
        self.vehicle = vehicle
        self.health = health
        self.sequence = initial_sequence

    def collect_once(self) -> Sample:
        self.sequence += 1
        sample = Sample(
            sequence=self.sequence,
            recorded_at=datetime.now(UTC),
            position=self.position.read(),
            metrics=dict(self.vehicle.read_metrics()),
            device=dict(self.health.read_health()),
        )
        self.queue.enqueue(sample)
        return sample

    def upload_once(self, limit: int = 500) -> int:
        samples = self.queue.pending(limit)
        if not samples:
            return 0
        acknowledged = self.transport.upload(samples)
        return self.queue.acknowledge(acknowledged)


class StaticVehicleProvider:
    def __init__(self, metrics: Mapping[str, object] | None = None):
        self.metrics = metrics or {}

    def read_metrics(self) -> Mapping[str, object]:
        return self.metrics
