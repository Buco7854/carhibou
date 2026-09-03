from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from backend.app.agents.models import Agent, AgentEnrollmentToken
from backend.app.auth.security import hash_token
from backend.app.common.time import utcnow
from backend.app.connectors.constants import MASKED_PASSWORD, TESLAMATE_IMPLEMENTATION_ID
from backend.app.connectors.models import Connector
from backend.app.connectors.services import connector_password

CONFIG = {
    "host": "mqtt.example.test",
    "port": 1883,
    "tls": False,
    "tls_accept_invalid_certs": False,
    "username": "teslamate",
    "namespace": "fleet",
    "car_id": 1,
    "sample_seconds": 10,
}


def _login(app: object, email: str) -> tuple[TestClient, str]:
    session = TestClient(app)  # type: ignore[arg-type]
    response = session.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "connector-test-password"},
    )
    assert response.status_code == 200, response.text
    return session, response.json()["csrf_token"]


def test_connector_api_access_password_and_shadow_agent(
    registered: tuple[TestClient, str], db_factory: sessionmaker[Session]
) -> None:
    admin, admin_csrf = registered
    headers = {"X-CSRF-Token": admin_csrf}
    vehicle = admin.post("/api/v1/vehicles", headers=headers, json={"name": "Model 3"}).json()
    users: dict[str, dict[str, object]] = {}
    for persona in ("operator", "viewer", "stranger"):
        created = admin.post(
            "/api/v1/users",
            headers=headers,
            json={
                "email": f"{persona}@example.com",
                "display_name": persona.title(),
                "password": "connector-test-password",
            },
        )
        assert created.status_code == 201, created.text
        users[persona] = created.json()
    grant = admin.put(
        f"/api/v1/vehicles/{vehicle['id']}/access",
        headers=headers,
        json=[
            {"user_id": users["operator"]["id"], "level": "operate"},
            {"user_id": users["viewer"]["id"], "level": "view"},
        ],
    )
    assert grant.status_code == 200, grant.text
    sessions = {
        "admin": (admin, admin_csrf),
        **{
            persona: _login(admin.app, f"{persona}@example.com")
            for persona in ("operator", "viewer", "stranger")
        },
    }

    for session, _csrf in sessions.values():
        catalog = session.get("/api/v1/connector-kinds")
        assert catalog.status_code == 200
        assert catalog.json()[0]["id"] == "teslamate.mqtt"

    operator, operator_csrf = sessions["operator"]
    created = operator.post(
        f"/api/v1/vehicles/{vehicle['id']}/connectors",
        headers={"X-CSRF-Token": operator_csrf},
        json={
            "kind": "teslamate.mqtt",
            "name": "Garage broker",
            "config": CONFIG,
            "password": "outbound-secret",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["config"] == CONFIG
    assert body["masked"] == MASKED_PASSWORD
    assert "password" not in body
    connector_id = body["id"]

    with db_factory() as db:
        connector = db.get(Connector, connector_id)
        agent = db.get(Agent, connector_id)
        assert connector and connector.encrypted_password
        assert "outbound-secret" not in connector.encrypted_password
        assert connector_password(connector) == "outbound-secret"
        assert agent
        assert agent.implementation_id == TESLAMATE_IMPLEMENTATION_ID
        assert agent.protocol_version == 2
        assert agent.sampling_seconds == 10

    assert admin.get("/api/v1/connectors").json()[0]["id"] == connector_id
    assert operator.get("/api/v1/connectors").json()[0]["id"] == connector_id
    assert sessions["viewer"][0].get("/api/v1/connectors").json()[0]["id"] == connector_id
    assert sessions["stranger"][0].get("/api/v1/connectors").json() == []
    assert all(item["id"] != connector_id for item in admin.get("/api/v1/agents").json())

    viewer, viewer_csrf = sessions["viewer"]
    denied = viewer.put(
        f"/api/v1/connectors/{connector_id}",
        headers={"X-CSRF-Token": viewer_csrf},
        json={"name": "No", "enabled": False, "config": CONFIG},
    )
    assert denied.status_code == 403
    stranger, stranger_csrf = sessions["stranger"]
    hidden = stranger.delete(
        f"/api/v1/connectors/{connector_id}",
        headers={"X-CSRF-Token": stranger_csrf},
    )
    assert hidden.status_code == 404

    updated_config = {**CONFIG, "sample_seconds": 25}
    updated = operator.put(
        f"/api/v1/connectors/{connector_id}",
        headers={"X-CSRF-Token": operator_csrf},
        json={"name": "Updated", "enabled": False, "config": updated_config},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["config_version"] == 2
    assert updated.json()["status"] == "disabled"
    assert updated.json()["masked"] == MASKED_PASSWORD
    with db_factory() as db:
        shadow = db.get(Agent, connector_id)
        connector = db.get(Connector, connector_id)
        assert shadow and shadow.sampling_seconds == 25
        assert connector and connector_password(connector) == "outbound-secret"

    agent_write = {
        "name": "Wrong realm",
        "sampling_seconds": 25,
        "upload_seconds": 25,
        "parked_sampling_seconds": 25,
        "parked_upload_seconds": 25,
    }
    assert (
        operator.put(
            f"/api/v1/agents/{connector_id}",
            headers={"X-CSRF-Token": operator_csrf},
            json=agent_write,
        ).status_code
        == 400
    )
    for suffix in ("revoke", "rotate"):
        assert (
            operator.post(
                f"/api/v1/agents/{connector_id}/{suffix}",
                headers={"X-CSRF-Token": operator_csrf},
            ).status_code
            == 400
        )
    assert (
        operator.delete(
            f"/api/v1/agents/{connector_id}",
            headers={"X-CSRF-Token": operator_csrf},
        ).status_code
        == 400
    )

    # Removing retires by default: the rows stay so the readings keep naming the
    # source that produced them. Purging is the other choice, asked for by name.
    retired = operator.delete(
        f"/api/v1/connectors/{connector_id}",
        headers={"X-CSRF-Token": operator_csrf},
    )
    assert retired.status_code == 204
    with db_factory() as db:
        assert db.get(Connector, connector_id) is not None
        agent = db.get(Agent, connector_id)
        assert agent is not None and agent.retired_at is not None

    purged = operator.delete(
        f"/api/v1/connectors/{connector_id}?purge_telemetry=true",
        headers={"X-CSRF-Token": operator_csrf},
    )
    assert purged.status_code == 204
    with db_factory() as db:
        assert db.get(Connector, connector_id) is None
        assert db.get(Agent, connector_id) is None


def test_connector_validation_fails_closed(registered: tuple[TestClient, str]) -> None:
    client, csrf = registered
    headers = {"X-CSRF-Token": csrf}
    vehicle = client.post("/api/v1/vehicles", headers=headers, json={"name": "Car"}).json()
    endpoint = f"/api/v1/vehicles/{vehicle['id']}/connectors"
    for config in (
        {**CONFIG, "host": "https://broker.example"},
        {**CONFIG, "port": 0},
        {**CONFIG, "unknown": True},
        {**CONFIG, "tls_accept_invalid_certs": True},
    ):
        response = client.post(
            endpoint,
            headers=headers,
            json={"kind": "teslamate.mqtt", "name": "Bad", "config": config},
        )
        assert response.status_code == 422
    unknown = client.post(
        endpoint,
        headers=headers,
        json={"kind": "unknown.mqtt", "name": "Bad", "config": CONFIG},
    )
    assert unknown.status_code == 422


def test_reserved_connector_enrollment_rejection_does_not_consume_token(
    registered: tuple[TestClient, str], db_factory: sessionmaker[Session]
) -> None:
    client, csrf = registered
    vehicle = client.post(
        "/api/v1/vehicles",
        headers={"X-CSRF-Token": csrf},
        json={"name": "Reserved test"},
    ).json()
    raw = "venroll_reserved_connector_test"
    now = utcnow()
    with db_factory() as db:
        token = AgentEnrollmentToken(
            token_hash=hash_token(raw),
            vehicle_id=vehicle["id"],
            intended_name="Reserved",
            implementation_id=TESLAMATE_IMPLEMENTATION_ID,
            created_at=now,
            expires_at=now + timedelta(minutes=10),
        )
        db.add(token)
        db.commit()
        token_id = token.id
    response = client.post(
        "/api/v1/agent/enroll",
        json={
            "token": raw,
            "implementation_id": TESLAMATE_IMPLEMENTATION_ID,
            "protocol_version": 2,
            "agent_version": "forbidden",
            "hostname": "",
        },
    )
    assert response.status_code == 400
    with db_factory() as db:
        assert db.get(AgentEnrollmentToken, token_id).used_at is None  # type: ignore[union-attr]
