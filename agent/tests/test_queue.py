from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent.vehicle_agent.models import Sample
from agent.vehicle_agent.queue import SQLiteQueue
from agent.vehicle_agent.runtime import AgentRuntime


class EmptyPosition:
    def read(self):  # type: ignore[no-untyped-def]
        return None


class EmptyVehicle:
    def read_metrics(self):  # type: ignore[no-untyped-def]
        return {"battery.soc": 50}


class EmptyHealth:
    def read_health(self):  # type: ignore[no-untyped-def]
        return {}


class RecoveringTransport:
    def __init__(self) -> None:
        self.available = False
        self.received: list[str] = []

    def upload(self, samples):  # type: ignore[no-untyped-def]
        if not self.available:
            raise ConnectionError("simulated cellular outage")
        self.received.extend(sample.id for sample in samples)
        return [sample.id for sample in samples]


def sample(sequence: int) -> Sample:
    return Sample(
        sequence=sequence,
        recorded_at=datetime.now(UTC),
        position=None,
        metrics={"battery.soc": 70 - sequence},
    )


def test_sqlite_queue_survives_restart_and_acknowledges_ids(tmp_path: Path) -> None:
    path = tmp_path / "queue.sqlite3"
    queue = SQLiteQueue(path)
    rows = [sample(1), sample(2)]
    for row in rows:
        queue.enqueue(row)
    queue.close()

    reopened = SQLiteQueue(path)
    assert [row.id for row in reopened.pending()] == [row.id for row in rows]
    assert reopened.acknowledge([rows[0].id]) == 1
    assert reopened.depth() == 1


def test_network_loss_preserves_samples_then_catches_up(tmp_path: Path) -> None:
    queue = SQLiteQueue(tmp_path / "queue.sqlite3")
    transport = RecoveringTransport()
    runtime = AgentRuntime(queue, transport, EmptyPosition(), EmptyVehicle(), EmptyHealth())
    runtime.collect_once()
    runtime.collect_once()
    with pytest.raises(ConnectionError):
        runtime.upload_once()
    assert queue.depth() == 2

    transport.available = True
    assert runtime.upload_once() == 2
    assert queue.depth() == 0
    assert len(transport.received) == 2
