from fastapi import APIRouter, HTTPException, status

from backend.app.access.dependencies import RequireAdmin, RequireAdminWrite
from backend.app.access.schemas import DefaultAccess, VehicleGrantResponse, VehicleGrantWrite
from backend.app.access.services import (
    AccessConfigurationError,
    get_default_access,
    list_vehicle_grants,
    replace_vehicle_grants,
    set_default_access,
)
from backend.app.auth.dependencies import Db
from backend.app.vehicles.models import Vehicle

router = APIRouter(tags=["access"])


def _vehicle(db: Db, vehicle_id: str) -> Vehicle:
    vehicle = db.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="vehicle not found")
    return vehicle


@router.get("/vehicles/{vehicle_id}/access", response_model=list[VehicleGrantResponse])
def vehicle_access(vehicle_id: str, db: Db, auth: RequireAdmin) -> list[VehicleGrantResponse]:
    del auth
    _vehicle(db, vehicle_id)
    return list_vehicle_grants(db, vehicle_id)


@router.put("/vehicles/{vehicle_id}/access", response_model=list[VehicleGrantResponse])
def update_vehicle_access(
    vehicle_id: str,
    grants: list[VehicleGrantWrite],
    db: Db,
    auth: RequireAdminWrite,
) -> list[VehicleGrantResponse]:
    del auth
    _vehicle(db, vehicle_id)
    try:
        response = replace_vehicle_grants(db, vehicle_id, grants)
    except AccessConfigurationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return response


@router.get("/admin/default-access", response_model=DefaultAccess)
def default_access(db: Db, auth: RequireAdmin) -> DefaultAccess:
    del auth
    return get_default_access(db)


@router.put("/admin/default-access", response_model=DefaultAccess)
def update_default_access(value: DefaultAccess, db: Db, auth: RequireAdminWrite) -> DefaultAccess:
    del auth
    try:
        response = set_default_access(db, value)
    except AccessConfigurationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return response
