from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from backend.app.access.constants import OPERATE, VehicleAccessLevel, level_allows
from backend.app.access.dependencies import OperateVehicle
from backend.app.access.services import access_level, visible_vehicle_ids
from backend.app.auth.dependencies import CurrentDevice, CurrentUser, CurrentUserWrite, Db
from backend.app.common.settings import get_settings
from backend.app.common.time import as_utc, utcnow
from backend.app.devices.models import Device
from backend.app.devices.protocol import (
    compatibility,
    describe,
    registered_implementations,
    render_steps,
)
from backend.app.devices.schemas import (
    AgentImplementation,
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
    delete_device,
    device_config,
    enroll,
    enrollment_implementation,
    rotate_credential,
    update_device,
)
from backend.app.users.models import User
from backend.app.vehicles.models import Vehicle

human_router = APIRouter(tags=["devices"])
device_router = APIRouter(prefix="/device", tags=["device API"])


def _authorized_device(db: Db, user: User, device_id: str, required: VehicleAccessLevel) -> Device:
    device = db.get(Device, device_id)
    level = access_level(db, user, device.vehicle_id) if device else None
    if not device or level is None:
        raise HTTPException(status_code=404, detail="device not found")
    if not level_allows(level, required):
        raise HTTPException(status_code=403, detail="permission denied")
    return device


@human_router.post(
    "/vehicles/{vehicle_id}/enrollments",
    response_model=EnrollmentCreated,
    status_code=status.HTTP_201_CREATED,
)
def new_enrollment(
    vehicle_id: str, data: EnrollmentCreate, db: Db, authorized: OperateVehicle
) -> EnrollmentCreated:
    try:
        implementation = enrollment_implementation(data.implementation_id)
        raw, token = create_enrollment(db, authorized.vehicle, data)
    except EnrollmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    rendered = render_steps(implementation, raw)
    db.commit()
    return EnrollmentCreated(token=raw, expires_at=token.expires_at, setup_steps=rendered)


@human_router.get("/agent-implementations", response_model=list[AgentImplementation])
def list_agent_implementations(auth: CurrentUser) -> list[AgentImplementation]:
    return [
        AgentImplementation.model_validate(describe(implementation))
        for implementation in registered_implementations()
    ]


def _device_response(device: Device, now: datetime | None = None) -> DeviceResponse:
    moment = now or utcnow()
    threshold = get_settings().default_online_threshold_seconds
    return DeviceResponse.model_validate(
        {
            **{
                field: getattr(device, field)
                for field in DeviceResponse.model_fields
                if field not in {"online", "compatibility"}
            },
            "compatibility": compatibility(device.protocol_version),
            "online": bool(
                device.revoked_at is None
                and device.last_seen_at
                and (moment - as_utc(device.last_seen_at)).total_seconds() <= threshold
            ),
        }
    )


@human_router.get("/devices", response_model=list[DeviceResponse])
def list_devices(db: Db, auth: CurrentUser) -> list[DeviceResponse]:
    visible = visible_vehicle_ids(db, auth.user)
    if not visible:
        return []
    devices = db.scalars(select(Device).where(Device.vehicle_id.in_(visible)))
    now = utcnow()
    return [_device_response(device, now) for device in devices]


@human_router.put("/devices/{device_id}", response_model=DeviceResponse)
def edit_device(
    device_id: str, data: DeviceSettings, db: Db, auth: CurrentUserWrite
) -> DeviceResponse:
    device = _authorized_device(db, auth.user, device_id, OPERATE)
    update_device(device, data)
    db.commit()
    db.refresh(device)
    return _device_response(device)


@human_router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_device(device_id: str, db: Db, auth: CurrentUserWrite) -> None:
    """Delete an agent outright, with the telemetry it recorded.

    Revoking is for hardware that exists but must stop reporting; this is for
    hardware that is gone, or that was enrolled by mistake and should leave
    nothing behind.
    """

    delete_device(db, _authorized_device(db, auth.user, device_id, OPERATE))
    db.commit()


@human_router.post("/devices/{device_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
def revoke_device(device_id: str, db: Db, auth: CurrentUserWrite) -> None:
    device = _authorized_device(db, auth.user, device_id, OPERATE)
    device.revoked_at = utcnow()
    db.commit()


@human_router.post("/devices/{device_id}/rotate", response_model=RotateCredentialResponse)
def rotate_device(device_id: str, db: Db, auth: CurrentUserWrite) -> RotateCredentialResponse:
    device = _authorized_device(db, auth.user, device_id, OPERATE)
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
