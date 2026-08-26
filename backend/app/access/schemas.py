from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class VehicleGrantWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    level: Literal["view", "operate"]


class VehicleGrantResponse(VehicleGrantWrite):
    email: str
    display_name: str


class DefaultVehicleGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vehicle_id: str
    level: Literal["view", "operate"]


class DefaultAccess(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profiles_create: bool = False
    grants: list[DefaultVehicleGrant] = Field(default_factory=list)
