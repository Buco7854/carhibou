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
    # An enum turns a raw value into a meaning. That meaning is a label when the
    # signal is for display and a boolean when it is one the agent reasons about,
    # so a profile can say "on this vehicle, four means ready" without the agent
    # needing to know what any particular vehicle calls its states.
    enum: dict[str, str | bool | float] | None = None


class ProfileSignal(BaseModel):
    """One mapping from a CAN frame to a canonical metric.

    A profile carries what decoding needs and the label the interface shows for
    it, and nothing else. Evidence statuses, source URLs, per-signal prose and a
    vehicle family were all carried here once and read by nothing.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120, pattern=r"^[a-z][a-z0-9_.-]*$")
    display_name: str = Field(default="", max_length=120)
    source: ProfileSource
    decoder: ProfileDecoder
    unit: str | None = Field(default=None, max_length=40)
    minimum: float | None = None
    maximum: float | None = None


class ComputedMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120, pattern=r"^[a-z][a-z0-9_.-]*$")
    operation: Literal["multiply"]
    inputs: Annotated[list[str], Field(min_length=2, max_length=2)]
    # Converts the raw product into the declared unit, e.g. volts times amps to kilowatts.
    scale: float = Field(default=1, gt=-1e6, lt=1e6)
    unit: str | None = Field(default=None, max_length=40)


class ProfileDefinition(BaseModel):
    # Forbidding extras is what keeps a retired field from surviving in a stored
    # definition and reappearing in the payload every agent downloads.
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=120)
    version: int = Field(default=1, ge=1, le=1_000_000)
    description: str = Field(default="", max_length=1000)
    signals: Annotated[list[ProfileSignal], Field(min_length=1, max_length=100)]
    computed_metrics: Annotated[list[ComputedMetric], Field(max_length=50)] = Field(
        default_factory=list
    )


class VehicleProfileWrite(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    signals: Annotated[list[ProfileSignal], Field(min_length=1, max_length=100)]
    computed_metrics: Annotated[list[ComputedMetric], Field(max_length=50)] = Field(
        default_factory=list
    )


class VehicleProfileResponse(BaseModel):
    id: str
    name: str
    description: str
    built_in: bool
    editable: bool
    definition: dict[str, Any]
    created_at: datetime | None = None
    updated_at: datetime | None = None


class VehicleProfileSelection(BaseModel):
    profile_id: str | None = Field(default=None, max_length=120)
