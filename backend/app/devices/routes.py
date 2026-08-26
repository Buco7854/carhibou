from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from backend.app.auth.dependencies import CurrentDevice, CurrentUser, CurrentUserWrite, Db
from backend.app.common.settings import get_settings
from backend.app.common.time import as_utc, utcnow
from backend.app.devices.models import Device
from backend.app.devices.schemas import (
    DeviceConfig,
    DeviceResponse,
    DeviceSettings,
    EnrollmentCreate,
    EnrollmentCreated,
    EnrollRequest,
    EnrollResponse,
    RotateCredentialResponse,
)
from backend.app.devices.services import (
    EnrollmentError,
    create_enrollment,
    device_config,
    enroll,
    install_command,
    rotate_credential,
    update_device,
)
from backend.app.vehicles.models import Vehicle
from backend.app.vehicles.services import owned_vehicle

human_router = APIRouter(tags=["devices"])
device_router = APIRouter(prefix="/device", tags=["device API"])


def _owned_device(db: Db, owner_id: str, device_id: str) -> Device:
    device = db.scalar(
        select(Device).join(Vehicle).where(Device.id == device_id, Vehicle.owner_id == owner_id)
    )
    if not device:
        raise HTTPException(status_code=404, detail="device not found")
    return device


@human_router.post(
    "/vehicles/{vehicle_id}/enrollments",
    response_model=EnrollmentCreated,
    status_code=status.HTTP_201_CREATED,
)
def new_enrollment(
    vehicle_id: str, data: EnrollmentCreate, db: Db, auth: CurrentUserWrite
) -> EnrollmentCreated:
    vehicle = owned_vehicle(db, auth.user.id, vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="vehicle not found")
    raw, token = create_enrollment(db, vehicle, data)
    db.commit()
    return EnrollmentCreated(
        token=raw, expires_at=token.expires_at, install_command=install_command(raw)
    )


def _device_response(device: Device, now: datetime | None = None) -> DeviceResponse:
    moment = now or utcnow()
    threshold = get_settings().default_online_threshold_seconds
    return DeviceResponse.model_validate(
        {
            **{
                field: getattr(device, field)
                for field in DeviceResponse.model_fields
                if field != "online"
            },
            "online": bool(
                device.revoked_at is None
                and device.last_seen_at
                and (moment - as_utc(device.last_seen_at)).total_seconds() <= threshold
            ),
        }
    )


@human_router.get("/devices", response_model=list[DeviceResponse])
def list_devices(db: Db, auth: CurrentUser) -> list[DeviceResponse]:
    devices = db.scalars(select(Device).join(Vehicle).where(Vehicle.owner_id == auth.user.id))
    now = utcnow()
    return [_device_response(device, now) for device in devices]


@human_router.put("/devices/{device_id}", response_model=DeviceResponse)
def edit_device(
    device_id: str, data: DeviceSettings, db: Db, auth: CurrentUserWrite
) -> DeviceResponse:
    device = _owned_device(db, auth.user.id, device_id)
    update_device(device, data)
    db.commit()
    db.refresh(device)
    return _device_response(device)


@human_router.post("/devices/{device_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
def revoke_device(device_id: str, db: Db, auth: CurrentUserWrite) -> None:
    device = _owned_device(db, auth.user.id, device_id)
    device.revoked_at = utcnow()
    db.commit()


@human_router.post("/devices/{device_id}/rotate", response_model=RotateCredentialResponse)
def rotate_device(device_id: str, db: Db, auth: CurrentUserWrite) -> RotateCredentialResponse:
    device = _owned_device(db, auth.user.id, device_id)
    if device.revoked_at:
        raise HTTPException(status_code=409, detail="revoked device cannot rotate credentials")
    credential = rotate_credential(device)
    db.commit()
    return RotateCredentialResponse(
        credential=credential, credential_version=device.credential_version
    )


@device_router.post("/enroll", response_model=EnrollResponse, status_code=status.HTTP_201_CREATED)
def enroll_device(data: EnrollRequest, db: Db) -> EnrollResponse:
    try:
        response = enroll(db, data)
    except EnrollmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return response


@device_router.get("/config", response_model=DeviceConfig)
def get_config(device: CurrentDevice, db: Db) -> DeviceConfig:
    vehicle = db.get(Vehicle, device.vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="vehicle not found")
    device.last_config_sync_at = utcnow()
    db.commit()
    return device_config(db, device, vehicle)
