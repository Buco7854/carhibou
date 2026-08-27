import re
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

from backend.app.telemetry.values import MetricValue

PROFILE_KEY = r"^[a-z][a-z0-9_.-]*$"
MAPPING_KEY = r"^[A-Za-z0-9_.-]+$"
POSITION_TARGETS = {
    "position.latitude",
    "position.longitude",
    "position.altitude",
    "position.speed",
    "position.heading",
    "position.accuracy",
}


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

    name: str = Field(min_length=1, max_length=120, pattern=PROFILE_KEY)
    display_name: str = Field(default="", max_length=120)
    source: ProfileSource
    decoder: ProfileDecoder
    unit: str | None = Field(default=None, max_length=40)
    minimum: float | None = None
    maximum: float | None = None


class ComputedMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120, pattern=PROFILE_KEY)
    operation: Literal["multiply"]
    inputs: Annotated[list[str], Field(min_length=2, max_length=2)]
    # Converts the raw product into the declared unit, such as volts times amps to kilowatts.
    scale: float = Field(default=1, gt=-1e6, lt=1e6)
    unit: str | None = Field(default=None, max_length=40)


class MappingTransform(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    scale: float | None = None
    offset: float | None = None
    enum: dict[str, MetricValue] | None = None
    boolean: Literal[True] | None = None
    json_flatten: Literal[True] | None = Field(default=None, alias="json")

    @model_validator(mode="after")
    def one_transform_kind(self) -> "MappingTransform":
        scalar = self.scale is not None or self.offset is not None
        modes = sum(
            (scalar, self.enum is not None, self.boolean is True, self.json_flatten is True)
        )
        if modes > 1:
            raise ValueError("mapping transform kinds cannot be combined")
        return self


class MappingRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    match: str = Field(min_length=1, max_length=120, pattern=MAPPING_KEY)
    target: str = Field(min_length=1, max_length=120)
    transform: MappingTransform | None = None

    @model_validator(mode="after")
    def valid_target(self) -> "MappingRule":
        if self.target == "position":
            if not self.transform or not self.transform.json_flatten:
                raise ValueError("position target requires a json transform")
            return self
        if self.target in POSITION_TARGETS:
            if self.transform and (
                self.transform.enum or self.transform.boolean or self.transform.json_flatten
            ):
                raise ValueError("position fields accept only numeric transforms")
            return self
        if not re.fullmatch(PROFILE_KEY, self.target):
            raise ValueError("mapping target is invalid")
        return self


class ProfileDefinitionBase(BaseModel):
    # Forbidding extras is what keeps a retired field from surviving in a stored
    # definition and reappearing in the payload every source downloads.
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=120)
    version: int = Field(default=1, ge=1, le=1_000_000)
    description: str = Field(default="", max_length=1000)


class CanProfileDefinition(ProfileDefinitionBase):
    type: Literal["can"]
    signals: Annotated[list[ProfileSignal], Field(min_length=1, max_length=100)]
    computed_metrics: Annotated[list[ComputedMetric], Field(max_length=50)] = Field(
        default_factory=list
    )


class MappingProfileDefinition(ProfileDefinitionBase):
    type: Literal["mapping"]
    passthrough_prefix: str = Field(default="", max_length=100, pattern=r"^(?:[a-z][a-z0-9_.-]*)?$")
    ignore: Annotated[list[str], Field(max_length=500)] = Field(default_factory=list)
    rules: Annotated[list[MappingRule], Field(max_length=500)] = Field(default_factory=list)

    @field_validator("ignore")
    @classmethod
    def unique_ignored_keys(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("ignored mapping keys must be unique")
        for value in values:
            if len(value) > 120 or not re.fullmatch(MAPPING_KEY, value):
                raise ValueError("ignored mapping key is invalid")
        return values

    @model_validator(mode="after")
    def unique_matches(self) -> "MappingProfileDefinition":
        matches = [rule.match for rule in self.rules]
        if len(matches) != len(set(matches)):
            raise ValueError("mapping rule matches must be unique")
        if set(matches) & set(self.ignore):
            raise ValueError("mapping keys cannot be both ignored and mapped")
        return self


ProfileDefinition = Annotated[
    CanProfileDefinition | MappingProfileDefinition, Field(discriminator="type")
]
PROFILE_DEFINITION_ADAPTER: TypeAdapter[ProfileDefinition] = TypeAdapter(ProfileDefinition)


class CanProfileWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["can"]
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    signals: Annotated[list[ProfileSignal], Field(min_length=1, max_length=100)]
    computed_metrics: Annotated[list[ComputedMetric], Field(max_length=50)] = Field(
        default_factory=list
    )


class MappingProfileWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["mapping"]
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    passthrough_prefix: str = Field(default="", max_length=100, pattern=r"^(?:[a-z][a-z0-9_.-]*)?$")
    ignore: Annotated[list[str], Field(max_length=500)] = Field(default_factory=list)
    rules: Annotated[list[MappingRule], Field(max_length=500)] = Field(default_factory=list)


VehicleProfileWrite = Annotated[CanProfileWrite | MappingProfileWrite, Field(discriminator="type")]


class VehicleProfileResponse(BaseModel):
    id: str
    name: str
    description: str
    type: Literal["can", "mapping"]
    built_in: bool
    editable: bool
    definition: dict[str, Any]
    created_at: datetime | None = None
    updated_at: datetime | None = None
