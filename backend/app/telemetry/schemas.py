from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

MetricValue = float | int | bool | str | None


class Position(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    altitude: float | None = Field(default=None, ge=-500, le=15000)
    speed: float | None = Field(default=None, ge=0, le=1000)
    heading: float | None = Field(default=None, ge=0, lt=360)
    accuracy: float | None = Field(default=None, ge=0, le=100000)


class TelemetrySample(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    id: UUID
    sequence: int = Field(ge=0)
    recorded_at: datetime
    position: Position | None = None
    metrics: dict[str, MetricValue] = Field(default_factory=dict)
    device: dict[str, MetricValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_metric_names(self) -> "TelemetrySample":
        for name in (*self.metrics, *self.device):
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
