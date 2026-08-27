import secrets

from sqlalchemy.orm import Session

from backend.app.agents.models import Agent
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


def create_connector(
    db: Session, vehicle: Vehicle, data: ConnectorCreate
) -> Connector:
    if data.kind != TESLAMATE_KIND:
        raise ValueError("connector kind is not available")
    connector = Connector(
        vehicle_id=vehicle.id,
        name=data.name,
        kind=data.kind,
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
            protocol_version=1,
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


def update_connector(
    db: Session, connector: Connector, data: ConnectorUpdate
) -> None:
    connector.name = data.name
    connector.enabled = data.enabled
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


def delete_connector(db: Session, connector: Connector) -> None:
    agent = db.get(Agent, connector.id)
    db.delete(connector)
    if agent:
        db.delete(agent)


def connector_password(connector: Connector) -> str | None:
    if not connector.encrypted_password:
        return None
    return decrypt_secret(connector.encrypted_password)

