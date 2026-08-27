from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.agents.models import Agent, AgentEnrollmentToken


def _vehicle(client: TestClient, csrf: str) -> dict[str, Any]:
    response = client.post(
        "/api/v1/vehicles",
        headers={"X-CSRF-Token": csrf},
        json={"name": "Protocol vehicle"},
    )
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


def _invitation(
    client: TestClient, csrf: str, vehicle_id: str, implementation_id: str
) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/vehicles/{vehicle_id}/enrollments",
        headers={"X-CSRF-Token": csrf},
        json={"implementation_id": implementation_id, "name": "Protocol agent"},
    )
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


def _enrollment_payload(invitation: dict[str, Any], implementation_id: str) -> dict[str, Any]:
    return {
        "token": invitation["token"],
        "implementation_id": implementation_id,
        "protocol_version": 1,
        "agent_version": "99.42.7-experimental",
        "hostname": "third-party-host",
        "hardware": {"board": "test"},
    }


def test_catalog_and_selected_setup_are_concise(
    registered: tuple[TestClient, str],
) -> None:
    client, csrf = registered
    assert client.get("/api/v1/agent-implementations").status_code == 200
    catalog = client.get("/api/v1/agent-implementations").json()
    assert [entry["id"] for entry in catalog] == ["carhibou.go", "custom"]
    assert all(entry["protocol_version"] == 1 for entry in catalog)
    assert catalog[0]["setup_kind"] == "command"
    assert catalog[1]["setup_kind"] == "guided"

    vehicle = _vehicle(client, csrf)
    bundled = _invitation(client, csrf, vehicle["id"], "carhibou.go")
    assert "install_command" not in bundled
    assert [step["kind"] for step in bundled["setup_steps"]] == ["command"]
    command = bundled["setup_steps"][0]["command"]
    assert "carhibou-agent" not in command
    assert "--server" in command and "--token" in command and "--version" in command

    custom = _invitation(client, csrf, vehicle["id"], "custom")
    steps = custom["setup_steps"]
    assert [step["kind"] for step in steps] == ["value", "value", "value", "link"]
    assert steps[0]["value"] == "http://localhost:8000"
    assert steps[1]["value"] == custom["token"]
    assert steps[2]["value"] == "1"
    assert steps[3]["url"] == "http://localhost:8000/api/docs"


@pytest.mark.parametrize("implementation_id", ["carhibou.go", "custom"])
def test_bundled_and_custom_enrollment_persist_independent_identity(
    registered: tuple[TestClient, str],
    db_factory: sessionmaker[Session],
    implementation_id: str,
) -> None:
    client, csrf = registered
    vehicle = _vehicle(client, csrf)
    invitation = _invitation(client, csrf, vehicle["id"], implementation_id)
    payload = _enrollment_payload(invitation, implementation_id)

    enrolled = client.post("/api/v1/agent/enroll", json=payload)

    assert enrolled.status_code == 201, enrolled.text
    listed = client.get("/api/v1/agents").json()[0]
    assert listed["implementation_id"] == implementation_id
    assert listed["protocol_version"] == 1
    assert listed["agent_version"] == "99.42.7-experimental"
    assert listed["compatibility"] == "compatible"
    with db_factory() as db:
        agent = db.scalar(select(Agent))
        assert agent is not None
        assert (agent.implementation_id, agent.protocol_version, agent.agent_version) == (
            implementation_id,
            1,
            "99.42.7-experimental",
        )


@pytest.mark.parametrize(
    ("field", "wrong", "message"),
    [
        ("implementation_id", "carhibou.go", "different agent implementation"),
        ("protocol_version", 2, "unsupported protocol version 2"),
    ],
)
def test_mismatch_does_not_consume_token(
    registered: tuple[TestClient, str],
    db_factory: sessionmaker[Session],
    field: str,
    wrong: object,
    message: str,
) -> None:
    client, csrf = registered
    vehicle = _vehicle(client, csrf)
    invitation = _invitation(client, csrf, vehicle["id"], "custom")
    payload = _enrollment_payload(invitation, "custom")
    payload[field] = wrong

    rejected = client.post("/api/v1/agent/enroll", json=payload)

    assert rejected.status_code == 400
    assert message in rejected.json()["error"]["message"]
    with db_factory() as db:
        token = db.scalar(select(AgentEnrollmentToken))
        assert token is not None
        assert token.used_at is None

    accepted = client.post(
        "/api/v1/agent/enroll",
        json=_enrollment_payload(invitation, "custom"),
    )
    assert accepted.status_code == 201, accepted.text
    assert (
        client.post(
            "/api/v1/agent/enroll",
            json=_enrollment_payload(invitation, "custom"),
        ).status_code
        == 400
    )


def test_required_identity_fields_and_integer_protocol_are_fail_closed(
    registered: tuple[TestClient, str],
) -> None:
    client, csrf = registered
    vehicle = _vehicle(client, csrf)
    invitation = _invitation(client, csrf, vehicle["id"], "custom")
    payload = _enrollment_payload(invitation, "custom")

    for field in ("implementation_id", "protocol_version", "agent_version", "hostname"):
        missing = {key: value for key, value in payload.items() if key != field}
        assert client.post("/api/v1/agent/enroll", json=missing).status_code == 422
    for value in (True, "1", 1.0):
        invalid = {**payload, "protocol_version": value}
        assert client.post("/api/v1/agent/enroll", json=invalid).status_code == 422

    omitted_implementation = client.post(
        f"/api/v1/vehicles/{vehicle['id']}/enrollments",
        headers={"X-CSRF-Token": csrf},
        json={"name": "No compatibility default"},
    )
    assert omitted_implementation.status_code == 422


def test_catalog_is_human_only_and_agent_endpoints_remain_agent_only(
    registered: tuple[TestClient, str],
) -> None:
    client, csrf = registered
    vehicle = _vehicle(client, csrf)
    invitation = _invitation(client, csrf, vehicle["id"], "custom")
    enrolled = client.post(
        "/api/v1/agent/enroll", json=_enrollment_payload(invitation, "custom")
    ).json()
    agent_headers = {"Authorization": f"Agent {enrolled['credential']}"}

    assert client.get("/api/v1/agent/config").status_code == 401
    client.cookies.clear()
    assert client.get("/api/v1/agent-implementations", headers=agent_headers).status_code == 401
    assert client.get("/api/v1/agent/config", headers=agent_headers).status_code == 200
