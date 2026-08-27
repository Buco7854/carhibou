from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.telemetry.values import POSITION_RANGES, MetricValue


class Position(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

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


class TelemetrySample(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    id: UUID
    sequence: int = Field(ge=0)
    recorded_at: datetime
    position: Position | None = None
    metrics: dict[str, MetricValue] = Field(default_factory=dict)
    agent: dict[str, MetricValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_metric_names(self) -> "TelemetrySample":
        for name in (*self.metrics, *self.agent):
            if not name or len(name) > 120 or any(ch.isspace() for ch in name):
                raise ValueError(f"invalid metric name: {name!r}")
        return self


class TelemetryBatch(BaseModel):
    boot_id: UUID
    samples: Annotated[list[TelemetrySample], Field(min_length=1, max_length=500)]

    @model_validator(mode="after")
    def unique_sample_ids(self) -> "TelemetryBatch":
        ids = [sample.id for sample in self.samples]
        if len(ids) != len(set(ids)):
            raise ValueError("sample IDs must be unique within a batch")
        return self


class BatchResponse(BaseModel):
    accepted: list[str]
    duplicates: list[str]
    config_version: int
