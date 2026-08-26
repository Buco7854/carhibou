from fastapi.testclient import TestClient


def test_tracker_cadence_is_chosen_at_enrollment_and_editable_afterwards(
    registered: tuple[TestClient, str],
) -> None:
    client, csrf = registered
    headers = {"X-CSRF-Token": csrf}
    vehicle = client.post("/api/v1/vehicles", headers=headers, json={"name": "Van"}).json()

    enrollment = client.post(
        f"/api/v1/vehicles/{vehicle['id']}/enrollments",
        headers=headers,
        json={"name": "Van tracker", "sampling_seconds": 30, "upload_seconds": 300},
    )
    assert enrollment.status_code == 201, enrollment.text

    enrolled = client.post(
        "/api/v1/device/enroll",
        json={"token": enrollment.json()["token"], "agent_version": "test", "hostname": "pi"},
    ).json()
    # The tracker starts on the cadence it was enrolled with, not on a default it
    # would then have to be corrected away from.
    assert enrolled["config"]["sampling"]["default_seconds"] == 30
    assert enrolled["config"]["upload"]["default_seconds"] == 300
    assert enrolled["config"]["version"] == 1

    device_id = enrolled["device_id"]
    device_headers = {"Authorization": f"Device {enrolled['credential']}"}

    # Renaming is a label the tracker never sees, so it must not look like a new
    # configuration the tracker has to fetch and re-validate.
    renamed = client.put(
        f"/api/v1/devices/{device_id}",
        headers=headers,
        json={"name": "Renamed", "sampling_seconds": 30, "upload_seconds": 300},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "Renamed"
    assert renamed.json()["config_version"] == 1

    slowed = client.put(
        f"/api/v1/devices/{device_id}",
        headers=headers,
        json={"name": "Renamed", "sampling_seconds": 60, "upload_seconds": 900},
    ).json()
    assert slowed["config_version"] == 2
    config = client.get("/api/v1/device/config", headers=device_headers).json()
    assert config["version"] == 2
    assert config["sampling"]["default_seconds"] == 60
    assert config["upload"]["default_seconds"] == 900

    # The agent enforces the same bounds, so a value it would reject never leaves
    # the server as a configuration the tracker silently keeps ignoring.
    rejected = client.put(
        f"/api/v1/devices/{device_id}",
        headers=headers,
        json={"name": "Renamed", "sampling_seconds": 0, "upload_seconds": 900},
    )
    assert rejected.status_code == 422
