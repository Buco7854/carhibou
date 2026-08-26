from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ProfileSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["can"] = "can"
    can_id: int = Field(ge=0, le=0x1FFFFFFF)


class ProfileDecoder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    byte_offset: int = Field(default=0, ge=0, le=63)
    data_type: Literal["uint8", "uint16", "uint32", "int8", "int16", "int32", "bytes", "boolean"]
    endianness: Literal["big", "little"] = "big"
    scale: float = 1
    offset: float = 0
    length: int | None = Field(default=None, ge=1, le=64)
    bit: int | None = Field(default=None, ge=0, le=7)
    bit_mask: int | str | None = None
    shift: int | None = Field(default=None, ge=0, le=63)
    signed: bool = False
    enum: dict[str, str] | None = None


class ProfileSignalWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120, pattern=r"^[a-z][a-z0-9_.-]*$")
    display_name: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=1000)
    source: ProfileSource
    decoder: ProfileDecoder
    unit: str | None = Field(default=None, max_length=40)
    minimum: float | None = None
    maximum: float | None = None


class ProfileSignal(ProfileSignalWrite):
    model_config = ConfigDict(extra="allow")

    status: Literal["verified", "experimental", "unknown", "deprecated"] = "unknown"
    references: Annotated[list[str], Field(max_length=20)] = Field(default_factory=list)
    notes: str = Field(default="", max_length=1000)


class ComputedMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120, pattern=r"^[a-z][a-z0-9_.-]*$")
    operation: Literal["multiply"]
    inputs: Annotated[list[str], Field(min_length=2, max_length=2)]
    # Converts the raw product into the declared unit, e.g. volts times amps to kilowatts.
    scale: float = Field(default=1, gt=-1e6, lt=1e6)
    unit: str | None = Field(default=None, max_length=40)
    status: Literal["verified", "experimental", "unknown", "deprecated"] = "experimental"


class ProfileDefinition(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=120)
    family: str = Field(default="custom", max_length=120)
    version: int = Field(default=1, ge=1, le=1_000_000)
    description: str = Field(default="", max_length=1000)
    signals: Annotated[list[ProfileSignal], Field(min_length=1, max_length=100)]
    computed_metrics: Annotated[list[ComputedMetric], Field(max_length=50)] = Field(
        default_factory=list
    )


class VehicleProfileWrite(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    family: str = Field(default="custom", max_length=120)
    signals: Annotated[list[ProfileSignalWrite], Field(min_length=1, max_length=100)]
    computed_metrics: Annotated[list[ComputedMetric], Field(max_length=50)] = Field(
        default_factory=list
    )


class VehicleProfileResponse(BaseModel):
    id: str
    name: str
    description: str
    built_in: bool
    definition: dict[str, Any]
    created_at: datetime | None = None
    updated_at: datetime | None = None


class VehicleProfileSelection(BaseModel):
    profile_id: str | None = Field(default=None, max_length=120)
