from datetime import timedelta
from typing import cast

from sqlalchemy import delete, func, select
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
    RetiredSource,
)
from backend.app.auth.security import hash_token, new_opaque_token
from backend.app.common.time import as_utc, utcnow
from backend.app.connectors.constants import CONNECTOR_IMPLEMENTATION_PREFIX
from backend.app.telemetry.models import Telemetry
from backend.app.vehicle_profiles.services import can_profile_definition
from backend.app.vehicle_state.models import VehicleState
from backend.app.vehicles.models import Vehicle


class EnrollmentError(Exception):
    pass


def agent_config(db: Session, agent: Agent) -> AgentConfig:
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
        vehicle_profile=agent.vehicle_profile,
        vehicle_profile_definition=can_profile_definition(db, agent.vehicle_profile),
    )


def create_enrollment(
    db: Session, vehicle: Vehicle, data: EnrollmentCreate
) -> tuple[str, AgentEnrollmentToken]:
    if data.implementation_id.startswith(CONNECTOR_IMPLEMENTATION_PREFIX):
        raise EnrollmentError("connector implementation ids cannot be enrolled")
    if data.vehicle_profile and not can_profile_definition(db, data.vehicle_profile):
        raise EnrollmentError("CAN profile is not available")
    raw = new_opaque_token("venroll")
    now = utcnow()
    model = AgentEnrollmentToken(
        token_hash=hash_token(raw),
        vehicle_id=vehicle.id,
        intended_name=data.name,
        implementation_id=data.implementation_id,
        vehicle_profile=data.vehicle_profile,
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
        vehicle_profile=token.vehicle_profile,
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
        config=agent_config(db, agent),
    )


def update_agent(db: Session, agent: Agent, data: AgentSettings) -> bool:
    """Apply agent settings, reporting whether the agent has to be told.

    Renaming is a label change the agent never sees, so only a cadence change
    bumps the configuration version. Bumping it for every edit would make each
    rename look, from the agent's side, like a configuration it had to fetch
    and re-validate.
    """

    if data.vehicle_profile and not can_profile_definition(db, data.vehicle_profile):
        raise EnrollmentError("CAN profile is not available")
    agent.name = data.name
    configuration = (
        "vehicle_profile",
        "sampling_seconds",
        "upload_seconds",
        "parked_sampling_seconds",
        "parked_upload_seconds",
    )
    changed = any(getattr(agent, field) != getattr(data, field) for field in configuration)
    for field in configuration:
        setattr(agent, field, getattr(data, field))
    if changed:
        agent.config_version += 1
    return changed


def retire_agent(db: Session, agent: Agent) -> None:
    """Take a source out of service without taking its readings with it.

    This is what removing an agent means by default. The row survives because
    every observation, candidate and history disclosure it produced names it as
    the source, and a reading that cannot say where it came from is worth less
    than one that can. The credential is revoked in the same breath: retirement
    is permanent, so the hardware must not be able to come back on its own.
    """

    del db
    now = utcnow()
    agent.retired_at = now
    if agent.revoked_at is None:
        agent.revoked_at = now


def purge_agent(db: Session, agent: Agent) -> None:
    """Remove an agent and everything it ever reported.

    Deliberately destructive and never the default. Telemetry, observations and
    candidates cascade from the agent row, which is the point: an agent enrolled
    by mistake, or one whose readings were nonsense, should leave nothing behind.
    """

    db.delete(agent)


def retired_source_accounting(db: Session) -> list[RetiredSource]:
    """What each retired source still holds, in one query.

    Retired sources are where orphaned telemetry lives: data nothing will add to
    again, kept because it is still the vehicle's history. Somebody deciding
    whether to purge one needs to know how much of it there is and how old.
    """

    rows = db.execute(
        select(
            Agent.id,
            Agent.name,
            Agent.retired_at,
            func.count(Telemetry.id),
            func.min(Telemetry.recorded_at),
            func.max(Telemetry.recorded_at),
        )
        .outerjoin(Telemetry, Telemetry.agent_id == Agent.id)
        .where(Agent.retired_at.is_not(None))
        .group_by(Agent.id, Agent.name, Agent.retired_at)
        .order_by(Agent.retired_at.desc(), Agent.id)
    ).all()
    return [
        RetiredSource(
            source_id=source_id,
            name=name,
            retired_at=as_utc(retired_at),
            samples=samples,
            oldest=as_utc(oldest) if oldest else None,
            newest=as_utc(newest) if newest else None,
        )
        for source_id, name, retired_at, samples, oldest, newest in rows
    ]


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
