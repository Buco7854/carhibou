from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from backend.app.auth.services import create_local_user


def profile_payload(*, scale: float = 0.5) -> dict[str, object]:
    return {
        "type": "can",
        "name": "My documented EV",
        "description": "Signals verified against my own vehicle",
        "signals": [
            {
                "name": "battery.soc",
                "display_name": "Battery level",
                "source": {"type": "can", "can_id": 0x374},
                "decoder": {
                    "byte_offset": 1,
                    "data_type": "uint8",
                    "endianness": "big",
                    "scale": scale,
                    "offset": 0,
                },
                "unit": "%",
                "minimum": 0,
                "maximum": 100,
            }
        ],
        "computed_metrics": [],
    }


def mapping_payload(*, target: str = "battery.soc") -> dict[str, object]:
    return {
        "type": "mapping",
        "name": "Broker mapping",
        "description": "Maps a documented source stream",
        "passthrough_prefix": "source",
        "ignore": ["deprecated"],
        "rules": [
            {
                "match": "battery",
                "target": target,
                "transform": {"scale": 1, "offset": 0},
            }
        ],
    }


def test_owner_profile_reaches_agent_and_updates_config_version(
    registered: tuple[TestClient, str],
) -> None:
    client, csrf = registered
    headers = {"X-CSRF-Token": csrf}

    listed = client.get("/api/v1/vehicle-profiles")
    assert listed.status_code == 200
    assert any(profile["id"] == "citroen-c-zero-v1" for profile in listed.json())

    created = client.post("/api/v1/vehicle-profiles", headers=headers, json=profile_payload())
    assert created.status_code == 201, created.text
    profile = created.json()
    assert profile["built_in"] is False
    assert profile["definition"]["id"] == profile["id"]
    assert profile["definition"]["signals"][0]["display_name"] == "Battery level"

    vehicle = client.post("/api/v1/vehicles", headers=headers, json={"name": "Owner EV"}).json()
    enrollment = client.post(
        f"/api/v1/vehicles/{vehicle['id']}/enrollments",
        headers=headers,
        json={
            "implementation_id": "custom",
            "name": "Pi agent",
            "vehicle_profile": profile["id"],
        },
    ).json()
    enrolled = client.post(
        "/api/v1/agent/enroll",
        json={
            "token": enrollment["token"],
            "implementation_id": "custom",
            "protocol_version": 2,
            "agent_version": "test",
            "hostname": "pi",
        },
    )
    assert enrolled.status_code == 201, enrolled.text
    agent = enrolled.json()
    assert agent["config"]["version"] == 1
    assert agent["config"]["vehicle_profile"] == profile["id"]
    shipped = agent["config"]["vehicle_profile_definition"]
    assert shipped["signals"][0]["decoder"]["scale"] == 0.5
    # An agent decodes frames; it never renders a profile. Interface metadata is
    # kept out of the configuration it downloads and parses on every sync.
    assert set(shipped) == {"id", "signals"}
    assert set(shipped["signals"][0]) == {
        "name",
        "source",
        "decoder",
        "unit",
        "minimum",
        "maximum",
    }

    updated = client.put(
        f"/api/v1/vehicle-profiles/{profile['id']}",
        headers=headers,
        json=profile_payload(scale=0.25),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["definition"]["version"] == 2

    agent_headers = {"Authorization": f"Agent {agent['credential']}"}
    config = client.get("/api/v1/agent/config", headers=agent_headers)
    assert config.status_code == 200
    assert config.json()["version"] == 2
    assert config.json()["vehicle_profile_definition"]["signals"][0]["decoder"]["scale"] == 0.25

    agent_id = agent["agent_id"]
    settings = {
        "name": "Pi agent",
        "vehicle_profile": "citroen-c-zero-v1",
        "sampling_seconds": 5,
        "upload_seconds": 5,
        "parked_sampling_seconds": 300,
        "parked_upload_seconds": 300,
    }
    selected = client.put(f"/api/v1/agents/{agent_id}", headers=headers, json=settings)
    assert selected.status_code == 200, selected.text
    assert selected.json()["config_version"] == 3
    assert selected.json()["vehicle_profile"] == "citroen-c-zero-v1"
    settings["vehicle_profile"] = profile["id"]
    selected = client.put(f"/api/v1/agents/{agent_id}", headers=headers, json=settings)
    assert selected.status_code == 200, selected.text
    assert selected.json()["config_version"] == 4

    removed = client.delete(f"/api/v1/vehicle-profiles/{profile['id']}", headers=headers)
    assert removed.status_code == 204
    assert "vehicle_profile" not in client.get(f"/api/v1/vehicles/{vehicle['id']}").json()
    config_after = client.get("/api/v1/agent/config", headers=agent_headers).json()
    assert config_after["version"] == 5
    assert config_after["vehicle_profile"] is None
    assert config_after["vehicle_profile_definition"] is None


def test_profile_validation_rejects_guessed_or_malformed_signal_definitions(
    registered: tuple[TestClient, str],
) -> None:
    client, csrf = registered
    payload = profile_payload()
    signal = payload["signals"][0]  # type: ignore[index]
    signal["source"]["can_id"] = -1
    response = client.post(
        "/api/v1/vehicle-profiles",
        headers={"X-CSRF-Token": csrf},
        json=payload,
    )
    assert response.status_code == 422

    vehicle = client.post(
        "/api/v1/vehicles",
        headers={"X-CSRF-Token": csrf},
        json={"name": "No guessed mapping", "vehicle_profile": "made-up-profile"},
    )
    assert vehicle.status_code == 422

    actual_vehicle = client.post(
        "/api/v1/vehicles",
        headers={"X-CSRF-Token": csrf},
        json={"name": "Profile-free vehicle"},
    ).json()
    enrollment = client.post(
        f"/api/v1/vehicles/{actual_vehicle['id']}/enrollments",
        headers={"X-CSRF-Token": csrf},
        json={"implementation_id": "custom", "vehicle_profile": "made-up-profile"},
    )
    assert enrollment.status_code == 400
    mapping = client.post(
        "/api/v1/vehicle-profiles",
        headers={"X-CSRF-Token": csrf},
        json=mapping_payload(),
    ).json()
    wrong_type = client.post(
        f"/api/v1/vehicles/{actual_vehicle['id']}/enrollments",
        headers={"X-CSRF-Token": csrf},
        json={"implementation_id": "custom", "vehicle_profile": mapping["id"]},
    )
    assert wrong_type.status_code == 400


def test_mapping_profile_api_is_typed_and_versions_referencing_connectors(
    registered: tuple[TestClient, str],
) -> None:
    client, csrf = registered
    headers = {"X-CSRF-Token": csrf}
    profile_response = client.post(
        "/api/v1/vehicle-profiles", headers=headers, json=mapping_payload()
    )
    assert profile_response.status_code == 201, profile_response.text
    profile = profile_response.json()
    assert profile["type"] == "mapping"
    assert profile["definition"]["type"] == "mapping"
    assert profile["definition"]["rules"][0]["target"] == "battery.soc"

    vehicle = client.post("/api/v1/vehicles", headers=headers, json={"name": "Mapped"}).json()
    connector_config = {
        "host": "mqtt.example.test",
        "port": 1883,
        "tls": False,
        "tls_accept_invalid_certs": False,
        "username": "",
        "namespace": "",
        "car_id": 1,
        "sample_seconds": 10,
    }
    connector_response = client.post(
        f"/api/v1/vehicles/{vehicle['id']}/connectors",
        headers=headers,
        json={
            "kind": "teslamate.mqtt",
            "name": "Mapped broker",
            "mapping_profile": profile["id"],
            "config": connector_config,
        },
    )
    assert connector_response.status_code == 201, connector_response.text
    connector = connector_response.json()
    assert connector["mapping_profile"] == profile["id"]
    assert connector["config_version"] == 1

    changed = client.put(
        f"/api/v1/vehicle-profiles/{profile['id']}",
        headers=headers,
        json=mapping_payload(target="battery.level"),
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["definition"]["version"] == 2
    listed = client.get("/api/v1/connectors").json()[0]
    assert listed["config_version"] == 2

    wrong_type = client.put(
        f"/api/v1/vehicle-profiles/{profile['id']}",
        headers=headers,
        json=profile_payload(),
    )
    assert wrong_type.status_code == 422
    invalid_selection = client.put(
        f"/api/v1/connectors/{connector['id']}",
        headers=headers,
        json={
            "name": "Mapped broker",
            "enabled": True,
            "mapping_profile": "citroen-c-zero-v1",
            "config": connector_config,
        },
    )
    assert invalid_selection.status_code == 400

    removed = client.delete(f"/api/v1/vehicle-profiles/{profile['id']}", headers=headers)
    assert removed.status_code == 204
    reset = client.get("/api/v1/connectors").json()[0]
    assert reset["mapping_profile"] == "teslamate-mqtt-v1"
    assert reset["config_version"] == 3


def test_custom_profiles_are_global_but_only_the_creator_can_edit(
    registered: tuple[TestClient, str], db_factory: sessionmaker[Session]
) -> None:
    client, owner_csrf = registered
    created = client.post(
        "/api/v1/vehicle-profiles",
        headers={"X-CSRF-Token": owner_csrf},
        json=profile_payload(),
    ).json()
    assert (
        client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": owner_csrf}).status_code == 204
    )

    with db_factory() as db:
        create_local_user(
            db,
            "second-owner@example.com",
            "second-owner-password",
            "Second Owner",
            admin=False,
        )
        db.commit()
    logged_in = client.post(
        "/api/v1/auth/login",
        json={"email": "second-owner@example.com", "password": "second-owner-password"},
    )
    assert logged_in.status_code == 200
    second_csrf = logged_in.json()["csrf_token"]
    headers = {"X-CSRF-Token": second_csrf}

    visible_ids = {row["id"] for row in client.get("/api/v1/vehicle-profiles").json()}
    assert created["id"] in visible_ids
    visible = next(
        row for row in client.get("/api/v1/vehicle-profiles").json() if row["id"] == created["id"]
    )
    assert visible["editable"] is False
    assert (
        client.put(
            f"/api/v1/vehicle-profiles/{created['id']}",
            headers=headers,
            json=profile_payload(scale=0.25),
        ).status_code
        == 403
    )
    assert (
        client.delete(f"/api/v1/vehicle-profiles/{created['id']}", headers=headers).status_code
        == 403
    )
    assert (
        client.post("/api/v1/vehicle-profiles", headers=headers, json=profile_payload()).status_code
        == 403
    )
