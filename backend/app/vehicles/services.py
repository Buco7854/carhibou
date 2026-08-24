from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.common.settings import get_settings
from backend.app.common.time import as_utc, utcnow
from backend.app.dashboards.models import Dashboard
from backend.app.users.models import User
from backend.app.vehicle_state.models import VehicleState
from backend.app.vehicles.models import Vehicle, VehiclePhoto
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
            .options(selectinload(Vehicle.state), selectinload(Vehicle.photo))
            .order_by(Vehicle.created_at)
        )
    )


def owned_vehicle(db: Session, owner_id: str, vehicle_id: str) -> Vehicle | None:
    return db.scalar(
        select(Vehicle)
        .where(Vehicle.id == vehicle_id, Vehicle.owner_id == owner_id)
        .options(selectinload(Vehicle.state), selectinload(Vehicle.photo))
    )


def owned_vehicle_photo(db: Session, owner_id: str, vehicle_id: str) -> VehiclePhoto | None:
    return db.scalar(
        select(VehiclePhoto)
        .join(Vehicle, Vehicle.id == VehiclePhoto.vehicle_id)
        .where(VehiclePhoto.vehicle_id == vehicle_id, Vehicle.owner_id == owner_id)
    )


def replace_vehicle_photo(
    db: Session,
    vehicle_id: str,
    storage_key: str,
    media_type: str,
    size_bytes: int,
    etag: str,
) -> None:
    photo = db.get(VehiclePhoto, vehicle_id)
    if photo:
        photo.storage_key = storage_key
        photo.media_type = media_type
        photo.size_bytes = size_bytes
        photo.etag = etag
    else:
        db.add(
            VehiclePhoto(
                vehicle_id=vehicle_id,
                storage_key=storage_key,
                media_type=media_type,
                size_bytes=size_bytes,
                etag=etag,
            )
        )


def delete_vehicle_photo(db: Session, vehicle_id: str) -> bool:
    photo = db.get(VehiclePhoto, vehicle_id)
    if not photo:
        return False
    db.delete(photo)
    return True


def delete_vehicle(db: Session, vehicle: Vehicle) -> str | None:
    """Delete a vehicle graph and remove its fixed references from dashboard JSON."""
    dashboards = db.scalars(select(Dashboard).where(Dashboard.owner_id == vehicle.owner_id))
    for dashboard in dashboards:
        layout = dict(dashboard.layout)
        widgets = layout.get("widgets", [])
        if not isinstance(widgets, list):
            continue
        changed = False
        updated_widgets: list[object] = []
        for value in widgets:
            if isinstance(value, dict) and value.get("vehicle_id") == vehicle.id:
                widget = dict(value)
                widget.pop("vehicle_id", None)
                updated_widgets.append(widget)
                changed = True
            else:
                updated_widgets.append(value)
        if changed:
            dashboard.layout = {**layout, "widgets": updated_widgets}
    storage_key = vehicle.photo.storage_key if vehicle.photo else None
    db.delete(vehicle)
    return storage_key


def serialize_vehicle(vehicle: Vehicle) -> VehicleResponse:
    response = VehicleResponse.model_validate(
        {
            name: getattr(vehicle, name)
            for name in VehicleResponse.model_fields
            if name not in {"state", "photo_url"}
        }
    )
    if vehicle.photo:
        response.photo_url = f"/api/v1/vehicles/{vehicle.id}/photo?v={vehicle.photo.etag[:16]}"
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
