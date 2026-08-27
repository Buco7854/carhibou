from datetime import timedelta
from typing import cast

from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from backend.app.agents.manifests import AgentManifest
from backend.app.agents.models import Agent, AgentEnrollmentToken
from backend.app.agents.protocol import SUPPORTED_PROTOCOL_VERSION, implementation_by_id
from backend.app.agents.schemas import (
    AgentConfig,
    AgentSettings,
    EnrollmentCreate,
    EnrollRequest,
    EnrollResponse,
)
from backend.app.auth.security import hash_token, new_opaque_token
from backend.app.common.time import as_utc, utcnow
from backend.app.connectors.constants import CONNECTOR_IMPLEMENTATION_PREFIX
from backend.app.telemetry.models import Telemetry
from backend.app.vehicle_profiles.services import profile_definition
from backend.app.vehicle_state.models import VehicleState
from backend.app.vehicles.models import Vehicle


class EnrollmentError(Exception):
    pass


def agent_config(db: Session, agent: Agent, vehicle: Vehicle) -> AgentConfig:
    return AgentConfig(
        version=agent.config_version,
        sampling={
            "default_seconds": agent.sampling_seconds,
            "parked_seconds": agent.parked_sampling_seconds,
        },
        upload={
            "default_seconds": agent.upload_seconds,
            "parked_seconds": agent.parked_upload_seconds,
        },
        vehicle_profile=vehicle.vehicle_profile,
        vehicle_profile_definition=profile_definition(db, vehicle.vehicle_profile),
    )


def create_enrollment(
    db: Session, vehicle: Vehicle, data: EnrollmentCreate
) -> tuple[str, AgentEnrollmentToken]:
    if data.implementation_id.startswith(CONNECTOR_IMPLEMENTATION_PREFIX):
        raise EnrollmentError("connector implementation ids cannot be enrolled")
    raw = new_opaque_token("venroll")
    now = utcnow()
    model = AgentEnrollmentToken(
        token_hash=hash_token(raw),
        vehicle_id=vehicle.id,
        intended_name=data.name,
        implementation_id=data.implementation_id,
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
    if request.implementation_id.startswith(CONNECTOR_IMPLEMENTATION_PREFIX):
        raise EnrollmentError("connector implementation ids cannot be enrolled")
    if request.protocol_version != SUPPORTED_PROTOCOL_VERSION:
        raise EnrollmentError(
            f"unsupported protocol version {request.protocol_version}; "
            f"server supports {SUPPORTED_PROTOCOL_VERSION}"
        )
    now = utcnow()
    token = db.scalar(
        select(AgentEnrollmentToken)
        .where(AgentEnrollmentToken.token_hash == hash_token(request.token))
        .with_for_update()
    )
    if not token or token.used_at is not None or as_utc(token.expires_at) < now:
        raise EnrollmentError("enrollment token is invalid, expired, or already used")
    if request.implementation_id != token.implementation_id:
        raise EnrollmentError("enrollment token is bound to a different agent implementation")
    vehicle = db.get(Vehicle, token.vehicle_id)
    if not vehicle:
        raise EnrollmentError("vehicle no longer exists")
    credential = new_opaque_token("vagent")
    agent = Agent(
        vehicle_id=vehicle.id,
        name=token.intended_name,
        credential_hash=hash_token(credential),
        implementation_id=request.implementation_id,
        protocol_version=request.protocol_version,
        agent_version=request.agent_version,
        hostname=request.hostname,
        hardware=request.hardware,
        sampling_seconds=token.sampling_seconds,
        upload_seconds=token.upload_seconds,
        parked_sampling_seconds=token.parked_sampling_seconds,
        parked_upload_seconds=token.parked_upload_seconds,
    )
    token.used_at = now
    db.add(agent)
    db.flush()
    return EnrollResponse(
        agent_id=agent.id,
        vehicle_id=vehicle.id,
        credential=credential,
        config=agent_config(db, agent, vehicle),
    )


def update_agent(agent: Agent, data: AgentSettings) -> bool:
    """Apply agent settings, reporting whether the agent has to be told.

    Renaming is a label change the agent never sees, so only a cadence change
    bumps the configuration version. Bumping it for every edit would make each
    rename look, from the agent's side, like a configuration it had to fetch
    and re-validate.
    """

    agent.name = data.name
    cadence = (
        "sampling_seconds",
        "upload_seconds",
        "parked_sampling_seconds",
        "parked_upload_seconds",
    )
    changed = any(getattr(agent, field) != getattr(data, field) for field in cadence)
    for field in cadence:
        setattr(agent, field, getattr(data, field))
    if changed:
        agent.config_version += 1
    return changed


def delete_agent(db: Session, agent: Agent) -> None:
    """Remove an agent and the telemetry it recorded.

    Revoking keeps an agent's history and stops it reporting; deleting is for
    hardware that is gone. Telemetry cascades from the agent, so what the agent
    recorded goes with it, which is the point: an agent enrolled by mistake should
    leave nothing behind.
    """

    db.delete(agent)


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


def rotate_credential(agent: Agent) -> str:
    credential = new_opaque_token("vagent")
    agent.credential_hash = hash_token(credential)
    agent.credential_version += 1
    return credential


def enrollment_implementation(implementation_id: str) -> AgentManifest:
    if implementation_id.startswith(CONNECTOR_IMPLEMENTATION_PREFIX):
        raise EnrollmentError("connector implementation ids cannot be enrolled")
    implementation = implementation_by_id(implementation_id)
    if implementation is None:
        raise EnrollmentError("agent implementation is not available")
    if implementation.protocol_version != SUPPORTED_PROTOCOL_VERSION:
        raise EnrollmentError("agent implementation uses an unsupported protocol version")
    return implementation
