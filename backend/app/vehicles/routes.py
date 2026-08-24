import logging
from hashlib import sha256

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import FileResponse

from backend.app.auth.dependencies import CurrentUser, CurrentUserWrite, Db
from backend.app.vehicle_profiles.schemas import VehicleProfileSelection
from backend.app.vehicle_profiles.services import assign_profile, profile_definition
from backend.app.vehicles.photo_storage import photo_path, remove_photo_file, store_photo
from backend.app.vehicles.photos import PhotoValidationError, validate_photo
from backend.app.vehicles.schemas import VehicleCreate, VehicleResponse
from backend.app.vehicles.services import (
    create_vehicle,
    delete_vehicle,
    delete_vehicle_photo,
    list_vehicles,
    owned_vehicle,
    owned_vehicle_photo,
    replace_vehicle_photo,
    serialize_vehicle,
)

router = APIRouter(prefix="/vehicles", tags=["vehicles"])
logger = logging.getLogger(__name__)


@router.get("")
def vehicles(db: Db, auth: CurrentUser) -> list[VehicleResponse]:
    return [serialize_vehicle(vehicle) for vehicle in list_vehicles(db, auth.user.id)]


@router.post("", response_model=VehicleResponse, status_code=status.HTTP_201_CREATED)
def add_vehicle(data: VehicleCreate, db: Db, auth: CurrentUserWrite) -> VehicleResponse:
    if data.vehicle_profile and not profile_definition(db, auth.user.id, data.vehicle_profile):
        raise HTTPException(status_code=422, detail="vehicle profile is not available")
    vehicle = create_vehicle(db, auth.user, data)
    db.commit()
    return serialize_vehicle(vehicle)


@router.get("/{vehicle_id}", response_model=VehicleResponse)
def vehicle(vehicle_id: str, db: Db, auth: CurrentUser) -> VehicleResponse:
    model = owned_vehicle(db, auth.user.id, vehicle_id)
    if not model:
        raise HTTPException(status_code=404, detail="vehicle not found")
    return serialize_vehicle(model)


@router.delete("/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_vehicle(vehicle_id: str, db: Db, auth: CurrentUserWrite) -> None:
    model = owned_vehicle(db, auth.user.id, vehicle_id)
    if not model:
        raise HTTPException(status_code=404, detail="vehicle not found")
    storage_key = delete_vehicle(db, model)
    db.commit()
    if storage_key:
        try:
            remove_photo_file(storage_key)
        except (OSError, ValueError):
            logger.exception("vehicle deleted but its photo file could not be removed")


@router.put("/{vehicle_id}/profile", response_model=VehicleResponse)
def select_vehicle_profile(
    vehicle_id: str, data: VehicleProfileSelection, db: Db, auth: CurrentUserWrite
) -> VehicleResponse:
    model = owned_vehicle(db, auth.user.id, vehicle_id)
    if not model:
        raise HTTPException(status_code=404, detail="vehicle not found")
    if data.profile_id and not profile_definition(db, auth.user.id, data.profile_id):
        raise HTTPException(status_code=422, detail="vehicle profile is not available")
    assign_profile(db, model, data.profile_id)
    db.commit()
    return serialize_vehicle(model)


@router.put(
    "/{vehicle_id}/photo",
    status_code=status.HTTP_204_NO_CONTENT,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                media_type: {"schema": {"type": "string", "format": "binary"}}
                for media_type in ("image/jpeg", "image/png", "image/webp")
            },
        }
    },
)
async def upload_vehicle_photo(
    vehicle_id: str, request: Request, db: Db, auth: CurrentUserWrite
) -> None:
    model = owned_vehicle(db, auth.user.id, vehicle_id)
    if not model:
        raise HTTPException(status_code=404, detail="vehicle not found")
    content = await request.body()
    try:
        photo = validate_photo(content, request.headers.get("content-type", ""))
    except PhotoValidationError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    etag = sha256(content).hexdigest()
    old_storage_key = model.photo.storage_key if model.photo else None
    storage_key = store_photo(model.id, content, photo.media_type, etag)
    try:
        replace_vehicle_photo(db, model.id, storage_key, photo.media_type, len(content), etag)
        db.commit()
    except BaseException:
        db.rollback()
        if storage_key != old_storage_key:
            remove_photo_file(storage_key)
        raise
    if old_storage_key and old_storage_key != storage_key:
        remove_photo_file(old_storage_key)


@router.get("/{vehicle_id}/photo")
def vehicle_photo(vehicle_id: str, request: Request, db: Db, auth: CurrentUser) -> Response:
    photo = owned_vehicle_photo(db, auth.user.id, vehicle_id)
    if not photo:
        raise HTTPException(status_code=404, detail="vehicle photo not found")
    try:
        stored_path = photo_path(photo.storage_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="vehicle photo not found") from exc
    if not stored_path.is_file():
        raise HTTPException(status_code=404, detail="vehicle photo not found")
    etag = f'"{photo.etag}"'
    headers = {
        "Cache-Control": "private, max-age=86400",
        "ETag": etag,
        "Content-Length": str(photo.size_bytes),
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    return FileResponse(stored_path, media_type=photo.media_type, headers=headers)


@router.delete("/{vehicle_id}/photo", status_code=status.HTTP_204_NO_CONTENT)
def remove_vehicle_photo(vehicle_id: str, db: Db, auth: CurrentUserWrite) -> None:
    model = owned_vehicle(db, auth.user.id, vehicle_id)
    if not model:
        raise HTTPException(status_code=404, detail="vehicle not found")
    storage_key = model.photo.storage_key if model.photo else None
    if not delete_vehicle_photo(db, model.id):
        raise HTTPException(status_code=404, detail="vehicle photo not found")
    db.commit()
    if storage_key:
        remove_photo_file(storage_key)
