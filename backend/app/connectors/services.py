import secrets

from sqlalchemy.orm import Session

from backend.app.agents.models import Agent
from backend.app.agents.services import purge_agent, retire_agent
from backend.app.auth.security import hash_token
from backend.app.branding import APP_VERSION
from backend.app.connectors.constants import (
    MASKED_PASSWORD,
    TESLAMATE_IMPLEMENTATION_ID,
    TESLAMATE_KIND,
)
from backend.app.connectors.models import Connector
from backend.app.connectors.schemas import ConnectorCreate, ConnectorResponse, ConnectorUpdate
from backend.app.secrets.crypto import decrypt_secret, encrypt_secret
from backend.app.vehicle_profiles.services import mapping_profile_definition
from backend.app.vehicles.models import Vehicle


def connector_response(connector: Connector) -> ConnectorResponse:
    return ConnectorResponse.model_validate(
        {
            **{
                field: getattr(connector, field)
                for field in ConnectorResponse.model_fields
                if field != "masked"
            },
            "masked": MASKED_PASSWORD if connector.encrypted_password else "",
        }
    )


def create_connector(db: Session, vehicle: Vehicle, data: ConnectorCreate) -> Connector:
    if data.kind != TESLAMATE_KIND:
        raise ValueError("connector kind is not available")
    if not mapping_profile_definition(db, data.mapping_profile):
        raise ValueError("mapping profile is not available")
    connector = Connector(
        vehicle_id=vehicle.id,
        name=data.name,
        kind=data.kind,
        mapping_profile=data.mapping_profile,
        enabled=True,
        config=data.config.model_dump(mode="json"),
        encrypted_password=encrypt_secret(data.password) if data.password else None,
        status="connecting",
    )
    db.add(connector)
    db.flush()
    cadence = data.config.sample_seconds
    db.add(
        Agent(
            id=connector.id,
            vehicle_id=vehicle.id,
            name=data.name,
            credential_hash=hash_token(secrets.token_urlsafe(48)),
            implementation_id=TESLAMATE_IMPLEMENTATION_ID,
            protocol_version=2,
            agent_version=APP_VERSION,
            hostname=None,
            hardware={"connector_kind": data.kind},
            sampling_seconds=cadence,
            upload_seconds=cadence,
            parked_sampling_seconds=cadence,
            parked_upload_seconds=cadence,
        )
    )
    db.flush()
    return connector


def update_connector(db: Session, connector: Connector, data: ConnectorUpdate) -> None:
    # Retirement is permanent for a connector for the same reason it is for an
    # agent: its readings stay, and a source that could come back would start
    # adding to a history it had already closed.
    if connector_is_retired(db, connector):
        raise ValueError("retired connector cannot be changed")
    if not mapping_profile_definition(db, data.mapping_profile):
        raise ValueError("mapping profile is not available")
    connector.name = data.name
    connector.enabled = data.enabled
    connector.mapping_profile = data.mapping_profile
    connector.config = data.config.model_dump(mode="json")
    if data.password is not None:
        connector.encrypted_password = encrypt_secret(data.password) if data.password else None
    connector.config_version += 1
    connector.status = "connecting" if data.enabled else "disabled"
    connector.last_error = ""
    agent = db.get(Agent, connector.id)
    if not agent:
        raise RuntimeError("connector shadow agent is missing")
    cadence = data.config.sample_seconds
    agent.name = data.name
    agent.config_version += 1
    agent.sampling_seconds = cadence
    agent.upload_seconds = cadence
    agent.parked_sampling_seconds = cadence
    agent.parked_upload_seconds = cadence


def shadow_agent(db: Session, connector: Connector) -> Agent | None:
    """The source row a connector reports through.

    A connector is not a second kind of source. It enrols an agent row with its
    own id and reports through it, which is why one lifecycle serves both and why
    retirement is recorded in exactly one place.
    """

    return db.get(Agent, connector.id)


def connector_is_retired(db: Session, connector: Connector) -> bool:
    agent = shadow_agent(db, connector)
    return agent is not None and agent.retired_at is not None


def retire_connector(db: Session, connector: Connector) -> None:
    """Take a connector out of service and keep everything it collected.

    The retirement itself is the shared one: it is stamped on the source row, so
    a reading still names the connector that produced it and the retired-source
    accounting finds it without knowing what kind of source it was. Disabling the
    connector row is the local effect, and what stops the supervisor running it.
    """

    agent = shadow_agent(db, connector)
    if agent is not None:
        retire_agent(db, agent)
    connector.enabled = False
    connector.status = "disabled"


def purge_connector(db: Session, connector: Connector) -> None:
    """Remove a connector and everything it collected.

    The connector row is local; the telemetry cascades from the source row, which
    is why the destructive half is the shared one too.
    """

    agent = shadow_agent(db, connector)
    db.delete(connector)
    if agent is not None:
        purge_agent(db, agent)


def connector_password(connector: Connector) -> str | None:
    if not connector.encrypted_password:
        return None
    return decrypt_secret(connector.encrypted_password)
