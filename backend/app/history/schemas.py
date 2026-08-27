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


class HistoryEntry(BaseModel):
    id: str
    recorded_at: datetime
    sequence: int
    latitude: float | None
    longitude: float | None
    altitude: float | None
    speed: float | None
    heading: float | None
    accuracy: float | None
    metrics: dict[str, object]
    agent: dict[str, object]


class HistoryEntriesResponse(BaseModel):
    vehicle_id: str
    start: datetime
    end: datetime
    total: int
    limit: int
    offset: int
    metric_keys: list[str]
    agent_keys: list[str]
    entries: list[HistoryEntry]
