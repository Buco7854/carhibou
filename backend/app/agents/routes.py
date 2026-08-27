from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from backend.app.access.constants import OPERATE, VehicleAccessLevel, level_allows
from backend.app.access.dependencies import OperateVehicle
from backend.app.access.services import access_level, visible_vehicle_ids
from backend.app.agents.models import Agent
from backend.app.agents.protocol import (
    compatibility,
    describe,
    registered_implementations,
    render_steps,
)
from backend.app.agents.schemas import (
    AgentConfig,
    AgentImplementation,
    AgentResponse,
    AgentSettings,
    EnrollmentCreate,
    EnrollmentCreated,
    EnrollRequest,
    EnrollResponse,
    RotateCredentialResponse,
)
from backend.app.agents.services import (
    EnrollmentError,
    agent_config,
    create_enrollment,
    delete_agent,
    enroll,
    enrollment_implementation,
    rotate_credential,
    update_agent,
)
from backend.app.auth.dependencies import CurrentAgent, CurrentUser, CurrentUserWrite, Db
from backend.app.common.settings import get_settings
from backend.app.common.time import as_utc, utcnow
from backend.app.connectors.constants import CONNECTOR_IMPLEMENTATION_PREFIX
from backend.app.users.models import User
from backend.app.vehicles.models import Vehicle

human_router = APIRouter(tags=["agents"])
agent_router = APIRouter(prefix="/agent", tags=["agent API"])


def _authorized_agent(db: Db, user: User, agent_id: str, required: VehicleAccessLevel) -> Agent:
    agent = db.get(Agent, agent_id)
    level = access_level(db, user, agent.vehicle_id) if agent else None
    if not agent or level is None:
        raise HTTPException(status_code=404, detail="agent not found")
    if not level_allows(level, required):
        raise HTTPException(status_code=403, detail="permission denied")
    return agent


def _ordinary_agent(agent: Agent) -> Agent:
    if agent.implementation_id.startswith(CONNECTOR_IMPLEMENTATION_PREFIX):
        raise HTTPException(
            status_code=400, detail="connector-backed agents are managed as connectors"
        )
    return agent


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


def _agent_response(agent: Agent, now: datetime | None = None) -> AgentResponse:
    moment = now or utcnow()
    threshold = get_settings().default_online_threshold_seconds
    return AgentResponse.model_validate(
        {
            **{
                field: getattr(agent, field)
                for field in AgentResponse.model_fields
                if field not in {"online", "compatibility"}
            },
            "compatibility": compatibility(agent.protocol_version),
            "online": bool(
                agent.revoked_at is None
                and agent.last_seen_at
                and (moment - as_utc(agent.last_seen_at)).total_seconds() <= threshold
            ),
        }
    )


@human_router.get("/agents", response_model=list[AgentResponse])
def list_agents(db: Db, auth: CurrentUser) -> list[AgentResponse]:
    visible = visible_vehicle_ids(db, auth.user)
    if not visible:
        return []
    agents = db.scalars(
        select(Agent).where(
            Agent.vehicle_id.in_(visible),
            ~Agent.implementation_id.startswith(CONNECTOR_IMPLEMENTATION_PREFIX),
        )
    )
    now = utcnow()
    return [_agent_response(agent, now) for agent in agents]


@human_router.put("/agents/{agent_id}", response_model=AgentResponse)
def edit_agent(
    agent_id: str, data: AgentSettings, db: Db, auth: CurrentUserWrite
) -> AgentResponse:
    agent = _ordinary_agent(_authorized_agent(db, auth.user, agent_id, OPERATE))
    update_agent(agent, data)
    db.commit()
    db.refresh(agent)
    return _agent_response(agent)


@human_router.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_agent(agent_id: str, db: Db, auth: CurrentUserWrite) -> None:
    """Delete an agent outright, with the telemetry it recorded.

    Revoking is for hardware that exists but must stop reporting; this is for
    hardware that is gone, or that was enrolled by mistake and should leave
    nothing behind.
    """

    delete_agent(
        db, _ordinary_agent(_authorized_agent(db, auth.user, agent_id, OPERATE))
    )
    db.commit()


@human_router.post("/agents/{agent_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
def revoke_agent(agent_id: str, db: Db, auth: CurrentUserWrite) -> None:
    agent = _ordinary_agent(_authorized_agent(db, auth.user, agent_id, OPERATE))
    agent.revoked_at = utcnow()
    db.commit()


@human_router.post("/agents/{agent_id}/rotate", response_model=RotateCredentialResponse)
def rotate_agent(agent_id: str, db: Db, auth: CurrentUserWrite) -> RotateCredentialResponse:
    agent = _ordinary_agent(_authorized_agent(db, auth.user, agent_id, OPERATE))
    if agent.revoked_at:
        raise HTTPException(status_code=409, detail="revoked agent cannot rotate credentials")
    credential = rotate_credential(agent)
    db.commit()
    return RotateCredentialResponse(
        credential=credential, credential_version=agent.credential_version
    )


@agent_router.post("/enroll", response_model=EnrollResponse, status_code=status.HTTP_201_CREATED)
def enroll_agent(data: EnrollRequest, db: Db) -> EnrollResponse:
    try:
        response = enroll(db, data)
    except EnrollmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return response


@agent_router.get("/config", response_model=AgentConfig)
def get_config(agent: CurrentAgent, db: Db) -> AgentConfig:
    vehicle = db.get(Vehicle, agent.vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="vehicle not found")
    agent.last_config_sync_at = utcnow()
    db.commit()
    return agent_config(db, agent, vehicle)
