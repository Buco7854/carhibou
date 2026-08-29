from datetime import datetime

from pydantic import BaseModel

from backend.app.telemetry.schemas import (
    Channel,
    Method,
    ReadingResponse,
    ResolvedPositionResponse,
    SourceKind,
)
from backend.app.telemetry.values import MetricValue


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


class RecordedObservation(BaseModel):
    key: str
    value: MetricValue
    observed_at: datetime
    source_id: str
    source_kind: SourceKind
    channel: Channel
    method: Method


class RecordedPosition(BaseModel):
    value: dict[str, object]
    observed_at: datetime
    source_id: str
    source_kind: SourceKind
    channel: Channel
    method: Method


class HistoryObservationSample(BaseModel):
    id: str
    sequence: int
    recorded_at: datetime
    received_at: datetime
    source_id: str
    source_kind: SourceKind
    reporting_interval: int | None
    event_driven: bool
    position: RecordedPosition | None
    observations: list[RecordedObservation]
    agent: dict[str, object]


class HistoryObservationsResponse(BaseModel):
    vehicle_id: str
    start: datetime
    end: datetime
    total: int
    limit: int
    offset: int
    samples: list[HistoryObservationSample]


class HistoryTableRow(BaseModel):
    bucket_start: datetime
    bucket_end: datetime
    collapsed_buckets: int
    readings: dict[str, ReadingResponse]
    position: ResolvedPositionResponse | None
    agent: dict[str, object]


class HistoryTableResponse(BaseModel):
    vehicle_id: str
    start: datetime
    end: datetime
    step_seconds: int
    total: int
    limit: int
    offset: int
    rows: list[HistoryTableRow]
