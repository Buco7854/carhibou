from datetime import datetime

from pydantic import BaseModel


class HistoryPoint(BaseModel):
    id: str
    recorded_at: datetime
    latitude: float | None
    longitude: float | None
    speed: float | None
    heading: float | None
    metrics: dict[str, object]


class HistoryResponse(BaseModel):
    vehicle_id: str
    start: datetime
    end: datetime
    available_metrics: list[str]
    original_count: int
    points: list[HistoryPoint]
