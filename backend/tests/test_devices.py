from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient


def test_agent_cadence_is_chosen_at_enrollment_and_editable_afterwards(
    registered: tuple[TestClient, str],
) -> None:
    client, csrf = registered
    headers = {"X-CSRF-Token": csrf}
    vehicle = client.post("/api/v1/vehicles", headers=headers, json={"name": "Van"}).json()

    enrollment = client.post(
        f"/api/v1/vehicles/{vehicle['id']}/enrollments",
        headers=headers,
        json={
            "implementation_id": "custom",
            "name": "Van agent",
            "sampling_seconds": 30,
            "upload_seconds": 300,
            "parked_sampling_seconds": 120,
            "parked_upload_seconds": 1800,
        },
    )
    assert enrollment.status_code == 201, enrollment.text

    enrolled = client.post(
        "/api/v1/device/enroll",
        json={
            "token": enrollment.json()["token"],
            "implementation_id": "custom",
            "protocol_version": 1,
            "agent_version": "test",
            "hostname": "pi",
        },
    ).json()
    # The agent starts on the cadence it was enrolled with, not on a default it
    # would then have to be corrected away from.
    assert enrolled["config"]["sampling"]["default_seconds"] == 30
    assert enrolled["config"]["upload"]["default_seconds"] == 300
    # A parked vehicle is worth much less traffic, and the agent is told both.
    assert enrolled["config"]["sampling"]["parked_seconds"] == 120
    assert enrolled["config"]["upload"]["parked_seconds"] == 1800
    assert enrolled["config"]["version"] == 1

    device_id = enrolled["device_id"]
    device_headers = {"Authorization": f"Device {enrolled['credential']}"}

    # Renaming is a label the agent never sees, so it must not look like a new
    # configuration the agent has to fetch and re-validate.
    renamed = client.put(
        f"/api/v1/devices/{device_id}",
        headers=headers,
        json={
            "name": "Renamed",
            "sampling_seconds": 30,
            "upload_seconds": 300,
            "parked_sampling_seconds": 120,
            "parked_upload_seconds": 1800,
        },
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "Renamed"
    assert renamed.json()["config_version"] == 1

    slowed = client.put(
        f"/api/v1/devices/{device_id}",
        headers=headers,
        json={
            "name": "Renamed",
            "sampling_seconds": 60,
            "upload_seconds": 900,
            "parked_sampling_seconds": 120,
            "parked_upload_seconds": 1800,
        },
    ).json()
    assert slowed["config_version"] == 2
    config = client.get("/api/v1/device/config", headers=device_headers).json()
    assert config["version"] == 2
    assert config["sampling"]["default_seconds"] == 60
    assert config["upload"]["default_seconds"] == 900

    # Changing only the parked pair is still a configuration the agent needs.
    parked = client.put(
        f"/api/v1/devices/{device_id}",
        headers=headers,
        json={
            "name": "Renamed",
            "sampling_seconds": 60,
            "upload_seconds": 900,
            "parked_sampling_seconds": 600,
            "parked_upload_seconds": 3600,
        },
    ).json()
    assert parked["config_version"] == 3
    assert (
        client.get("/api/v1/device/config", headers=device_headers).json()["sampling"][
            "parked_seconds"
        ]
        == 600
    )

    # The agent enforces the same bounds, so a value it would reject never leaves
    # the server as a configuration the agent silently keeps ignoring.
    rejected = client.put(
        f"/api/v1/devices/{device_id}",
        headers=headers,
        json={
            "name": "Renamed",
            "sampling_seconds": 0,
            "upload_seconds": 900,
            "parked_sampling_seconds": 120,
            "parked_upload_seconds": 1800,
        },
    )
    assert rejected.status_code == 422


def test_a_agent_can_be_deleted_and_a_vehicle_emptied(
    registered: tuple[TestClient, str],
) -> None:
    client, csrf = registered
    headers = {"X-CSRF-Token": csrf}
    vehicle = client.post("/api/v1/vehicles", headers=headers, json={"name": "Test car"}).json()

    token = client.post(
        f"/api/v1/vehicles/{vehicle['id']}/enrollments",
        headers=headers,
        json={"implementation_id": "custom", "name": "Pi"},
    ).json()["token"]
    enrolled = client.post(
        "/api/v1/device/enroll",
        json={
            "token": token,
            "implementation_id": "custom",
            "protocol_version": 1,
            "agent_version": "test",
            "hostname": "pi",
        },
    ).json()
    credential = {"Authorization": f"Device {enrolled['credential']}"}
    sent = client.post(
        "/api/v1/device/telemetry/batch",
        headers=credential,
        json={
            "boot_id": str(uuid4()),
            "samples": [
                {
                    "id": str(uuid4()),
                    "sequence": 1,
                    "recorded_at": datetime.now(UTC).isoformat(),
                    "position": {"latitude": 48.0, "longitude": 2.0},
                    "metrics": {"battery.soc": 80},
                    "device": {},
                }
            ],
        },
    )
    assert sent.status_code == 200, sent.text

    entries = f"/api/v1/vehicles/{vehicle['id']}/history/entries"
    assert client.get(entries).json()["total"] == 1

    # Emptying a vehicle keeps the vehicle and its agent; only readings go.
    assert (
        client.delete(f"/api/v1/vehicles/{vehicle['id']}/telemetry", headers=headers).status_code
        == 204
    )
    assert client.get(entries).json()["total"] == 0
    assert client.get(f"/api/v1/vehicles/{vehicle['id']}").status_code == 200
    assert any(d["id"] == enrolled["device_id"] for d in client.get("/api/v1/devices").json())
    # The vehicle must stop claiming a reading nothing now supports.
    assert client.get(f"/api/v1/vehicles/{vehicle['id']}").json()["state"] is None

    # Deleting the agent is for hardware that is gone, and leaves nothing behind.
    removed = client.delete(f"/api/v1/devices/{enrolled['device_id']}", headers=headers)
    assert removed.status_code == 204, removed.text
    assert client.get("/api/v1/devices").json() == []
    # Its credential no longer works.
    assert client.get("/api/v1/device/config", headers=credential).status_code == 401


def test_every_vehicle_can_be_emptied_at_once(registered: tuple[TestClient, str]) -> None:
    client, csrf = registered
    headers = {"X-CSRF-Token": csrf}
    for name in ("One", "Two"):
        client.post("/api/v1/vehicles", headers=headers, json={"name": name})

    assert client.delete("/api/v1/vehicles/telemetry", headers=headers).status_code == 204
    # The vehicles themselves survive; this empties them rather than removing them.
    assert len(client.get("/api/v1/vehicles").json()) == 2
