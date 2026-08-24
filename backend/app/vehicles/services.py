from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.common.settings import get_settings
from backend.app.common.time import as_utc, utcnow
from backend.app.users.models import User
from backend.app.vehicle_state.models import VehicleState
from backend.app.vehicles.models import Vehicle
from backend.app.vehicles.schemas import (
    PositionResponse,
    StateResponse,
    VehicleCreate,
    VehicleResponse,
)


def create_vehicle(db: Session, owner: User, data: VehicleCreate) -> Vehicle:
    vehicle = Vehicle(owner_id=owner.id, **data.model_dump())
    db.add(vehicle)
    db.flush()
    return vehicle


def list_vehicles(db: Session, owner_id: str) -> list[Vehicle]:
    return list(
        db.scalars(
            select(Vehicle)
            .where(Vehicle.owner_id == owner_id)
            .options(selectinload(Vehicle.state))
            .order_by(Vehicle.created_at)
        )
    )


def owned_vehicle(db: Session, owner_id: str, vehicle_id: str) -> Vehicle | None:
    return db.scalar(
        select(Vehicle)
        .where(Vehicle.id == vehicle_id, Vehicle.owner_id == owner_id)
        .options(selectinload(Vehicle.state))
    )


def serialize_vehicle(vehicle: Vehicle) -> VehicleResponse:
    response = VehicleResponse.model_validate(
        {name: getattr(vehicle, name) for name in VehicleResponse.model_fields if name != "state"}
    )
    state: VehicleState | None = vehicle.state
    if not state:
        return response
    position = None
    if state.latitude is not None and state.longitude is not None:
        position = PositionResponse(
            latitude=state.latitude,
            longitude=state.longitude,
            altitude=state.altitude,
            speed=state.gps_speed,
            heading=state.heading,
            accuracy=state.accuracy,
        )
    online = as_utc(state.updated_at) >= utcnow() - timedelta(
        seconds=get_settings().default_online_threshold_seconds
    )
    response.state = StateResponse(
        updated_at=state.updated_at,
        online=online,
        position=position,
        metrics=state.latest_metrics,
        device=state.device_state,
    )
    return response
