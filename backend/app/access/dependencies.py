from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, status

from backend.app.access.constants import OPERATE, VehicleAccessLevel, level_allows
from backend.app.access.services import access_level, is_admin
from backend.app.auth.dependencies import (
    AuthenticatedUser,
    CurrentUser,
    CurrentUserWrite,
    Db,
)
from backend.app.vehicles.models import Vehicle


@dataclass(frozen=True)
class AuthorizedVehicle:
    vehicle: Vehicle
    authenticated: AuthenticatedUser
    level: VehicleAccessLevel


def require_admin(authenticated: CurrentUser) -> AuthenticatedUser:
    if not is_admin(authenticated.user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission denied")
    return authenticated


def require_admin_write(authenticated: CurrentUserWrite) -> AuthenticatedUser:
    if not is_admin(authenticated.user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission denied")
    return authenticated


RequireAdmin = Annotated[AuthenticatedUser, Depends(require_admin)]
RequireAdminWrite = Annotated[AuthenticatedUser, Depends(require_admin_write)]


def _authorize_vehicle(
    db: Db,
    authenticated: AuthenticatedUser,
    vehicle_id: str,
    required: VehicleAccessLevel,
) -> AuthorizedVehicle:
    vehicle = db.get(Vehicle, vehicle_id)
    level = access_level(db, authenticated.user, vehicle_id) if vehicle else None
    if not vehicle or level is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="vehicle not found")
    if not level_allows(level, required):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission denied")
    return AuthorizedVehicle(vehicle=vehicle, authenticated=authenticated, level=level)


def view_vehicle(vehicle_id: str, db: Db, authenticated: CurrentUser) -> AuthorizedVehicle:
    return _authorize_vehicle(db, authenticated, vehicle_id, "view")


def operate_vehicle(vehicle_id: str, db: Db, authenticated: CurrentUserWrite) -> AuthorizedVehicle:
    return _authorize_vehicle(db, authenticated, vehicle_id, OPERATE)


ViewVehicle = Annotated[AuthorizedVehicle, Depends(view_vehicle)]
OperateVehicle = Annotated[AuthorizedVehicle, Depends(operate_vehicle)]
