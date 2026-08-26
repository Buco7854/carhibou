from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from backend.app.auth.services import create_local_user


def profile_payload(*, scale: float = 0.5) -> dict[str, object]:
    return {
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
    assigned = client.put(
        f"/api/v1/vehicles/{vehicle['id']}/profile",
        headers=headers,
        json={"profile_id": profile["id"]},
    )
    assert assigned.status_code == 200

    enrollment = client.post(
        f"/api/v1/vehicles/{vehicle['id']}/enrollments",
        headers=headers,
        json={"name": "Pi agent"},
    ).json()
    enrolled = client.post(
        "/api/v1/device/enroll",
        json={"token": enrollment["token"], "agent_version": "test", "hostname": "pi"},
    )
    assert enrolled.status_code == 201, enrolled.text
    device = enrolled.json()
    assert device["config"]["version"] == 1
    assert device["config"]["vehicle_profile"] == profile["id"]
    shipped = device["config"]["vehicle_profile_definition"]
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

    device_headers = {"Authorization": f"Device {device['credential']}"}
    config = client.get("/api/v1/device/config", headers=device_headers)
    assert config.status_code == 200
    assert config.json()["version"] == 2
    assert config.json()["vehicle_profile_definition"]["signals"][0]["decoder"]["scale"] == 0.25

    removed = client.delete(f"/api/v1/vehicle-profiles/{profile['id']}", headers=headers)
    assert removed.status_code == 204
    vehicle_after = client.get(f"/api/v1/vehicles/{vehicle['id']}").json()
    assert vehicle_after["vehicle_profile"] is None
    config_after = client.get("/api/v1/device/config", headers=device_headers).json()
    assert config_after["version"] == 3
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


def test_custom_profiles_are_owner_scoped(
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
    assert created["id"] not in visible_ids
    assert (
        client.put(
            f"/api/v1/vehicle-profiles/{created['id']}",
            headers=headers,
            json=profile_payload(scale=0.25),
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/api/v1/vehicle-profiles/{created['id']}", headers=headers).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/vehicles",
            headers=headers,
            json={"name": "Other vehicle", "vehicle_profile": created["id"]},
        ).status_code
        == 422
    )
