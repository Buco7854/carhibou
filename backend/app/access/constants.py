from typing import Literal

SYSTEM_ADMIN = "system.admin"
PROFILES_CREATE = "profiles.create"

VehicleAccessLevel = Literal["view", "operate"]
VIEW: VehicleAccessLevel = "view"
OPERATE: VehicleAccessLevel = "operate"


def level_allows(actual: VehicleAccessLevel, required: VehicleAccessLevel) -> bool:
    return actual == OPERATE or required == VIEW
