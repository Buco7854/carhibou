import shlex
from datetime import timedelta
from typing import cast

from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from backend.app.auth.security import hash_token, new_opaque_token
from backend.app.branding import APP_VERSION
from backend.app.common.settings import get_settings
from backend.app.common.time import as_utc, utcnow
from backend.app.devices.models import Device, EnrollmentToken
from backend.app.devices.schemas import (
    DeviceConfig,
    DeviceSettings,
    EnrollmentCreate,
    EnrollRequest,
    EnrollResponse,
)
from backend.app.telemetry.models import Telemetry
from backend.app.vehicle_profiles.services import profile_definition
from backend.app.vehicle_state.models import VehicleState
from backend.app.vehicles.models import Vehicle


class EnrollmentError(Exception):
    pass


def device_config(db: Session, device: Device, vehicle: Vehicle) -> DeviceConfig:
    return DeviceConfig(
        version=device.config_version,
        sampling={
            "default_seconds": device.sampling_seconds,
            "parked_seconds": device.parked_sampling_seconds,
        },
        upload={
            "default_seconds": device.upload_seconds,
            "parked_seconds": device.parked_upload_seconds,
        },
        vehicle_profile=vehicle.vehicle_profile,
        vehicle_profile_definition=profile_definition(db, vehicle.vehicle_profile),
    )


def create_enrollment(
    db: Session, vehicle: Vehicle, data: EnrollmentCreate
) -> tuple[str, EnrollmentToken]:
    raw = new_opaque_token("venroll")
    now = utcnow()
    model = EnrollmentToken(
        token_hash=hash_token(raw),
        vehicle_id=vehicle.id,
        intended_name=data.name,
        created_at=now,
        expires_at=now + timedelta(minutes=data.ttl_minutes),
        sampling_seconds=data.sampling_seconds,
        upload_seconds=data.upload_seconds,
        parked_sampling_seconds=data.parked_sampling_seconds,
        parked_upload_seconds=data.parked_upload_seconds,
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
        sampling_seconds=token.sampling_seconds,
        upload_seconds=token.upload_seconds,
        parked_sampling_seconds=token.parked_sampling_seconds,
        parked_upload_seconds=token.parked_upload_seconds,
    )
    token.used_at = now
    db.add(device)
    db.flush()
    return EnrollResponse(
        device_id=device.id,
        vehicle_id=vehicle.id,
        credential=credential,
        config=device_config(db, device, vehicle),
    )


def update_device(device: Device, data: DeviceSettings) -> bool:
    """Apply agent settings, reporting whether the agent has to be told.

    Renaming is a label change the agent never sees, so only a cadence change
    bumps the configuration version. Bumping it for every edit would make each
    rename look, from the agent's side, like a configuration it had to fetch
    and re-validate.
    """

    device.name = data.name
    cadence = (
        "sampling_seconds",
        "upload_seconds",
        "parked_sampling_seconds",
        "parked_upload_seconds",
    )
    changed = any(getattr(device, field) != getattr(data, field) for field in cadence)
    for field in cadence:
        setattr(device, field, getattr(data, field))
    if changed:
        device.config_version += 1
    return changed


def delete_device(db: Session, device: Device) -> None:
    """Remove an agent and the telemetry it recorded.

    Revoking keeps an agent's history and stops it reporting; deleting is for
    hardware that is gone. Telemetry cascades from the device, so what the agent
    recorded goes with it, which is the point: an agent enrolled by mistake should
    leave nothing behind.
    """

    db.delete(device)


def reset_vehicle_telemetry(db: Session, vehicle_id: str) -> int:
    """Delete every reading recorded for one vehicle, keeping the vehicle.

    Its agents, hooks and dashboards are untouched, so a vehicle can be emptied
    of test data without being set up again. The current-state row goes with the
    readings, or the vehicle would keep showing a reading nothing now supports.
    """

    deleted = cast(
        CursorResult[tuple[()]],
        db.execute(delete(Telemetry).where(Telemetry.vehicle_id == vehicle_id)),
    )
    db.execute(delete(VehicleState).where(VehicleState.vehicle_id == vehicle_id))
    return deleted.rowcount


def rotate_credential(device: Device) -> str:
    credential = new_opaque_token("vdev")
    device.credential_hash = hash_token(credential)
    device.credential_version += 1
    return credential


def install_command(token: str) -> str:
    base = get_settings().public_url.rstrip("/")
    installer_url = shlex.quote(f"{base}/install-agent")
    insecure = " --allow-insecure-http" if base.startswith("http://") else ""
    return (
        f"curl -fsSL {installer_url} | sudo sh -s -- "
        f"--server {shlex.quote(base)} --token {shlex.quote(token)} --version {APP_VERSION}"
        f"{insecure}"
    )
