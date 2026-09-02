from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.telemetry.values import POSITION_RANGES, MetricValue

Channel = Literal["can", "obd", "gnss", "mqtt", "derived"]
Method = Literal["direct", "derived"]
SourceKind = Literal["agent", "connector"]


class Position(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")

    latitude: float = Field(
        ge=POSITION_RANGES["latitude"].minimum, le=POSITION_RANGES["latitude"].maximum
    )
    longitude: float = Field(
        ge=POSITION_RANGES["longitude"].minimum, le=POSITION_RANGES["longitude"].maximum
    )
    altitude: float | None = Field(
        default=None,
        ge=POSITION_RANGES["altitude"].minimum,
        le=POSITION_RANGES["altitude"].maximum,
    )
    speed: float | None = Field(
        default=None,
        ge=POSITION_RANGES["speed"].minimum,
        le=POSITION_RANGES["speed"].maximum,
    )
    heading: float | None = Field(
        default=None,
        ge=POSITION_RANGES["heading"].minimum,
        lt=POSITION_RANGES["heading"].maximum,
    )
    accuracy: float | None = Field(
        default=None,
        ge=POSITION_RANGES["accuracy"].minimum,
        le=POSITION_RANGES["accuracy"].maximum,
    )


class Observation(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")

    key: str = Field(min_length=1, max_length=120, pattern=r"^\S+$")
    value: MetricValue
    observed_at: datetime
    channel: Channel
    method: Method


class PositionObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Position
    observed_at: datetime
    channel: Channel
    method: Method


class TelemetrySample(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")

    id: UUID
    sequence: int = Field(ge=0)
    recorded_at: datetime
    position: PositionObservation | None = None
    observations: list[Observation] = Field(default_factory=list, max_length=2000)
    agent: dict[str, MetricValue] = Field(default_factory=dict)
    reporting_interval: int | None = Field(default=None, ge=1, le=86400)
    event_driven: bool = False

    @model_validator(mode="after")
    def validate_observations(self) -> "TelemetrySample":
        if self.event_driven and self.reporting_interval is not None:
            raise ValueError("event-driven samples cannot declare a reporting interval")
        pairs = [(item.key, item.channel) for item in self.observations]
        if len(pairs) != len(set(pairs)):
            raise ValueError("(key, channel) must be unique within a sample")
        for name in self.agent:
            if not name or len(name) > 120 or any(ch.isspace() for ch in name):
                raise ValueError(f"invalid agent field name: {name!r}")
        return self


class TelemetryBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    boot_id: UUID
    samples: Annotated[list[TelemetrySample], Field(min_length=1, max_length=500)]

    @model_validator(mode="after")
    def unique_sample_ids(self) -> "TelemetryBatch":
        ids = [sample.id for sample in self.samples]
        if len(ids) != len(set(ids)):
            raise ValueError("sample IDs must be unique within a batch")
        return self


class ReadingResponse(BaseModel):
    value: MetricValue
    observed_at: datetime
    source_id: str
    source_kind: SourceKind
    channel: Channel
    method: Method
    fresh: bool


class ResolvedPositionResponse(Position):
    observed_at: datetime
    source_id: str
    source_kind: SourceKind
    channel: Channel
    method: Method
    fresh: bool


class BatchResponse(BaseModel):
    accepted: list[str]
    duplicates: list[str]
    config_version: int


class MetricDefinitionResponse(BaseModel):
    key: str
    unit: str | None
    meaning: str
    kind: str
    value_type: str
    retained: bool
    freshness_seconds: int


class PositionFieldResponse(BaseModel):
    key: str
    unit: str
    meaning: str


class PositionDescriptorResponse(BaseModel):
    meaning: str
    fields: list[PositionFieldResponse]


class MetricRegistryResponse(BaseModel):
    metrics: list[MetricDefinitionResponse]
    position: PositionDescriptorResponse
