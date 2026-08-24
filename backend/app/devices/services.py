import shlex
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.auth.security import hash_token, new_opaque_token
from backend.app.branding import APP_VERSION
from backend.app.common.settings import get_settings
from backend.app.common.time import as_utc, utcnow
from backend.app.devices.models import Device, EnrollmentToken
from backend.app.devices.schemas import DeviceConfig, EnrollRequest, EnrollResponse
from backend.app.vehicles.models import Vehicle


class EnrollmentError(Exception):
    pass


def device_config(device: Device, vehicle: Vehicle) -> DeviceConfig:
    return DeviceConfig(
        version=device.config_version,
        sampling={"default_seconds": 5},
        upload={"default_seconds": 30},
        vehicle_profile=vehicle.vehicle_profile,
    )


def create_enrollment(
    db: Session, vehicle: Vehicle, name: str, ttl_minutes: int
) -> tuple[str, EnrollmentToken]:
    raw = new_opaque_token("venroll")
    now = utcnow()
    model = EnrollmentToken(
        token_hash=hash_token(raw),
        vehicle_id=vehicle.id,
        intended_name=name,
        created_at=now,
        expires_at=now + timedelta(minutes=ttl_minutes),
    )
    db.add(model)
    db.flush()
    return raw, model


def enroll(db: Session, request: EnrollRequest) -> EnrollResponse:
    now = utcnow()
    token = db.scalar(
        select(EnrollmentToken)
        .where(EnrollmentToken.token_hash == hash_token(request.token))
        .with_for_update()
    )
    if not token or token.used_at is not None or as_utc(token.expires_at) < now:
        raise EnrollmentError("enrollment token is invalid, expired, or already used")
    vehicle = db.get(Vehicle, token.vehicle_id)
    if not vehicle:
        raise EnrollmentError("vehicle no longer exists")
    credential = new_opaque_token("vdev")
    device = Device(
        vehicle_id=vehicle.id,
        name=token.intended_name,
        credential_hash=hash_token(credential),
        agent_version=request.agent_version,
        hostname=request.hostname,
        hardware=request.hardware,
    )
    token.used_at = now
    db.add(device)
    db.flush()
    return EnrollResponse(
        device_id=device.id,
        vehicle_id=vehicle.id,
        credential=credential,
        config=device_config(device, vehicle),
    )


def rotate_credential(device: Device) -> str:
    credential = new_opaque_token("vdev")
    device.credential_hash = hash_token(credential)
    device.credential_version += 1
    return credential


def install_command(token: str) -> str:
    base = get_settings().public_url.rstrip("/")
    installer_url = shlex.quote(f"{base}/install-agent")
    return (
        f"curl -fsSL {installer_url} | sudo sh -s -- "
        f"--server {shlex.quote(base)} --token {shlex.quote(token)} --version {APP_VERSION}"
    )
