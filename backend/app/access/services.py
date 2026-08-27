from typing import cast

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.access.constants import (
    OPERATE,
    PROFILES_CREATE,
    SYSTEM_ADMIN,
    VehicleAccessLevel,
)
from backend.app.access.models import AppSetting, VehicleAccessGrant
from backend.app.access.schemas import DefaultAccess, VehicleGrantResponse, VehicleGrantWrite
from backend.app.users.models import User
from backend.app.vehicles.models import Vehicle

DEFAULT_ACCESS_KEY = "default_access"


class AccessConfigurationError(ValueError):
    pass


def is_admin(user: User) -> bool:
    return bool(user.permissions.get(SYSTEM_ADMIN))


def permissions_for(user: User) -> dict[str, bool]:
    return {
        SYSTEM_ADMIN: is_admin(user),
        PROFILES_CREATE: user.can_create_profiles,
    }


def visible_vehicle_ids(db: Session, user: User) -> set[str]:
    if is_admin(user):
        return set(db.scalars(select(Vehicle.id)))
    return set(
        db.scalars(
            select(VehicleAccessGrant.vehicle_id).where(VehicleAccessGrant.user_id == user.id)
        )
    )


def access_level(db: Session, user: User, vehicle_id: str) -> VehicleAccessLevel | None:
    if db.get(Vehicle, vehicle_id) is None:
        return None
    if is_admin(user):
        return OPERATE
    level = db.scalar(
        select(VehicleAccessGrant.level).where(
            VehicleAccessGrant.user_id == user.id,
            VehicleAccessGrant.vehicle_id == vehicle_id,
        )
    )
    if level in {"view", "operate"}:
        return cast(VehicleAccessLevel, level)
    return None


def list_vehicle_grants(db: Session, vehicle_id: str) -> list[VehicleGrantResponse]:
    rows = db.execute(
        select(VehicleAccessGrant, User)
        .join(User, User.id == VehicleAccessGrant.user_id)
        .where(VehicleAccessGrant.vehicle_id == vehicle_id)
        .order_by(User.created_at)
    )
    return [
        VehicleGrantResponse(
            user_id=grant.user_id,
            email=user.email,
            display_name=user.display_name,
            level=cast(VehicleAccessLevel, grant.level),
        )
        for grant, user in rows
    ]


def replace_vehicle_grants(
    db: Session, vehicle_id: str, grants: list[VehicleGrantWrite]
) -> list[VehicleGrantResponse]:
    user_ids = [grant.user_id for grant in grants]
    if len(user_ids) != len(set(user_ids)):
        raise AccessConfigurationError("each user may have only one vehicle grant")
    existing_users = set(db.scalars(select(User.id).where(User.id.in_(user_ids))))
    if existing_users != set(user_ids):
        raise AccessConfigurationError("vehicle grant references an unknown user")
    db.execute(delete(VehicleAccessGrant).where(VehicleAccessGrant.vehicle_id == vehicle_id))
    db.add_all(
        VehicleAccessGrant(vehicle_id=vehicle_id, user_id=grant.user_id, level=grant.level)
        for grant in grants
    )
    db.flush()
    return list_vehicle_grants(db, vehicle_id)


def get_default_access(db: Session) -> DefaultAccess:
    setting = db.get(AppSetting, DEFAULT_ACCESS_KEY)
    return DefaultAccess.model_validate(setting.value if setting else {})


def set_default_access(db: Session, value: DefaultAccess) -> DefaultAccess:
    if len({grant.vehicle_id for grant in value.grants}) != len(value.grants):
        raise AccessConfigurationError("each vehicle may appear only once")
    setting = db.get(AppSetting, DEFAULT_ACCESS_KEY)
    serialized = value.model_dump(mode="json")
    if setting:
        setting.value = serialized
    else:
        db.add(AppSetting(key=DEFAULT_ACCESS_KEY, value=serialized))
    return value


def apply_default_access(db: Session, user: User) -> None:
    template = get_default_access(db)
    user.can_create_profiles = template.profiles_create
    requested = {grant.vehicle_id: grant.level for grant in template.grants}
    existing = set(db.scalars(select(Vehicle.id).where(Vehicle.id.in_(requested))))
    db.add_all(
        VehicleAccessGrant(vehicle_id=vehicle_id, user_id=user.id, level=requested[vehicle_id])
        for vehicle_id in existing
    )
