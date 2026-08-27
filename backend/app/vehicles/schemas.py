from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VehicleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    manufacturer: str = Field(default="", max_length=120)
    model: str = Field(default="", max_length=120)
    year: int | None = Field(default=None, ge=1886, le=2200)
    vin: str | None = Field(default=None, min_length=17, max_length=17)
    battery_nominal_capacity_kwh: float | None = Field(default=None, gt=0, le=1000)
    vehicle_profile: str | None = Field(default=None, max_length=120)
    timezone: str = Field(default="UTC", max_length=64)
    color: str = Field(default="#62d4a7", pattern=r"^#[0-9a-fA-F]{6}$")

    @field_validator("vin")
    @classmethod
    def normalize_vin(cls, value: str | None) -> str | None:
        return value.upper() if value else None


class PositionResponse(BaseModel):
    latitude: float
    longitude: float
    altitude: float | None = None
    speed: float | None = None
    heading: float | None = None
    accuracy: float | None = None


class StateResponse(BaseModel):
    updated_at: datetime
    online: bool
    position: PositionResponse | None
    metrics: dict[str, object]
    agent: dict[str, object]


class VehicleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    manufacturer: str
    model: str
    year: int | None
    vin: str | None
    battery_nominal_capacity_kwh: float | None
    vehicle_profile: str | None
    timezone: str
    color: str
    icon: str
    access: Literal["view", "operate"]
    photo_url: str | None = None
    created_at: datetime
    updated_at: datetime
    state: StateResponse | None = None
