from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class PositionFix:
    latitude: float
    longitude: float
    recorded_at: datetime | None = None
    altitude: float | None = None
    speed: float | None = None
    heading: float | None = None
    accuracy: float | None = None
    fix_quality: int | None = None
    satellites: int | None = None

    def as_telemetry(self) -> dict[str, object]:
        value = asdict(self)
        value.pop("recorded_at")
        value.pop("fix_quality")
        value.pop("satellites")
        return {key: item for key, item in value.items() if item is not None}


@dataclass(frozen=True)
class Sample:
    sequence: int
    recorded_at: datetime
    position: PositionFix | None
    metrics: dict[str, Any] = field(default_factory=dict)
    device: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))

    def as_payload(self) -> dict[str, object]:
        return {
            "id": self.id,
            "sequence": self.sequence,
            "recorded_at": self.recorded_at.isoformat(),
            "position": self.position.as_telemetry() if self.position else None,
            "metrics": self.metrics,
            "device": self.device,
        }


@dataclass(frozen=True)
class CANFrame:
    timestamp: float
    can_id: int
    data: bytes

    def as_dict(self) -> dict[str, object]:
        return {
            "type": "frame",
            "timestamp": self.timestamp,
            "can_id": f"0x{self.can_id:03X}",
            "data": self.data.hex().upper(),
        }
