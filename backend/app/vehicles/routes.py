from fastapi import APIRouter, HTTPException, status

from backend.app.auth.dependencies import CurrentUser, CurrentUserWrite, Db
from backend.app.vehicles.schemas import VehicleCreate, VehicleResponse
from backend.app.vehicles.services import (
    create_vehicle,
    list_vehicles,
    owned_vehicle,
    serialize_vehicle,
)

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


@router.get("")
def vehicles(db: Db, auth: CurrentUser) -> list[VehicleResponse]:
    return [serialize_vehicle(vehicle) for vehicle in list_vehicles(db, auth.user.id)]


@router.post("", response_model=VehicleResponse, status_code=status.HTTP_201_CREATED)
def add_vehicle(data: VehicleCreate, db: Db, auth: CurrentUserWrite) -> VehicleResponse:
    vehicle = create_vehicle(db, auth.user, data)
    db.commit()
    return serialize_vehicle(vehicle)


@router.get("/{vehicle_id}", response_model=VehicleResponse)
def vehicle(vehicle_id: str, db: Db, auth: CurrentUser) -> VehicleResponse:
    model = owned_vehicle(db, auth.user.id, vehicle_id)
    if not model:
        raise HTTPException(status_code=404, detail="vehicle not found")
    return serialize_vehicle(model)
