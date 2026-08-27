import json
import sqlite3
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from agent.vehicle_agent.models import PositionFix, Sample


class SQLiteQueue:
    """Durable append/ack queue tuned to batch writes and WAL recovery."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.execute("PRAGMA busy_timeout=5000")
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS samples (
                id TEXT PRIMARY KEY,
                sequence INTEGER NOT NULL,
                recorded_at TEXT NOT NULL,
                payload TEXT NOT NULL,
                queued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.connection.commit()

    def enqueue(self, sample: Sample) -> None:
        self.connection.execute(
            "INSERT OR IGNORE INTO samples "
            "(id, sequence, recorded_at, payload) VALUES (?, ?, ?, ?)",
            (
                sample.id,
                sample.sequence,
                sample.recorded_at.isoformat(),
                json.dumps(sample.as_payload()),
            ),
        )
        self.connection.commit()

    def pending(self, limit: int = 500) -> list[Sample]:
        rows = self.connection.execute(
            "SELECT payload FROM samples ORDER BY sequence, queued_at LIMIT ?", (limit,)
        ).fetchall()
        return [self._deserialize(json.loads(row[0])) for row in rows]

    def acknowledge(self, sample_ids: Sequence[str]) -> int:
        if not sample_ids:
            return 0
        placeholders = ",".join("?" for _ in sample_ids)
        cursor = self.connection.execute(
            f"DELETE FROM samples WHERE id IN ({placeholders})",  # noqa: S608 - placeholders only
            tuple(sample_ids),
        )
        self.connection.commit()
        return cursor.rowcount

    def depth(self) -> int:
        row = self.connection.execute("SELECT COUNT(*) FROM samples").fetchone()
        return int(row[0]) if row else 0

    def close(self) -> None:
        self.connection.close()

    @staticmethod
    def _deserialize(payload: dict[str, object]) -> Sample:
        position_data = payload.get("position")
        position = PositionFix(**position_data) if isinstance(position_data, dict) else None
        metrics = payload.get("metrics", {})
        device = payload.get("device", {})
        return Sample(
            id=str(payload["id"]),
            sequence=int(str(payload["sequence"])),
            recorded_at=datetime.fromisoformat(str(payload["recorded_at"])),
            position=position,
            metrics=dict(metrics) if isinstance(metrics, dict) else {},
            device=dict(device) if isinstance(device, dict) else {},
        )
