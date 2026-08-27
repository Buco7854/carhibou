from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient


def _vehicle_and_device(client: TestClient, csrf: str) -> tuple[dict[str, Any], dict[str, Any]]:
    response = client.post(
        "/api/v1/vehicles",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": "Éclair",
            "manufacturer": "Citroën",
            "model": "C-Zero",
            "year": 2018,
            "battery_nominal_capacity_kwh": 16,
            "vehicle_profile": "citroen-c-zero-v1",
        },
    )
    assert response.status_code == 201, response.text
    vehicle = response.json()
    enrollment = client.post(
        f"/api/v1/vehicles/{vehicle['id']}/enrollments",
        headers={"X-CSRF-Token": csrf},
        json={"implementation_id": "custom", "name": "Pi Zero simulator"},
    )
    assert enrollment.status_code == 201, enrollment.text
    token = enrollment.json()["token"]
    enroll_data = {
        "token": token,
        "implementation_id": "custom",
        "protocol_version": 1,
        "agent_version": "0.1.0",
        "hostname": "simulator",
        "hardware": {"model": "simulated-pi-zero"},
    }
    enrolled = client.post("/api/v1/device/enroll", json=enroll_data)
    assert enrolled.status_code == 201, enrolled.text
    assert client.post("/api/v1/device/enroll", json=enroll_data).status_code == 400
    return vehicle, enrolled.json()


def test_idempotent_telemetry_current_state_history_and_dashboard(
    registered: tuple[TestClient, str],
) -> None:
    client, csrf = registered
    vehicle, enrolled = _vehicle_and_device(client, csrf)
    sample_id = str(uuid4())
    recorded = datetime.now(UTC) - timedelta(seconds=5)
    batch = {
        "boot_id": str(uuid4()),
        "samples": [
            {
                "id": sample_id,
                "sequence": 1,
                "recorded_at": recorded.isoformat(),
                "position": {
                    "latitude": 48.12345,
                    "longitude": 2.12345,
                    "speed": 42.5,
                    "heading": 120,
                },
                "metrics": {"battery.soc": 70, "battery.pack_voltage": 330.5},
                "device": {"mobile_signal": -82},
            }
        ],
    }
    headers = {"Authorization": f"Device {enrolled['credential']}"}
    first = client.post("/api/v1/device/telemetry/batch", headers=headers, json=batch)
    assert first.status_code == 200, first.text
    assert first.json()["accepted"] == [sample_id]
    retry = client.post("/api/v1/device/telemetry/batch", headers=headers, json=batch)
    assert retry.status_code == 200
    assert retry.json()["accepted"] == []
    assert retry.json()["duplicates"] == [sample_id]

    current = client.get(f"/api/v1/vehicles/{vehicle['id']}")
    assert current.status_code == 200
    assert current.json()["state"]["metrics"]["battery.soc"] == 70
    assert current.json()["state"]["position"]["latitude"] == 48.12345
    devices = client.get("/api/v1/devices").json()
    assert devices[0]["online"] is True

    history = client.get(f"/api/v1/vehicles/{vehicle['id']}/history")
    assert history.status_code == 200, history.text
    assert history.json()["original_count"] == 1
    assert "battery.soc" in history.json()["available_metrics"]

    dashboard = client.post(
        "/api/v1/dashboards",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": "Road trip",
            "is_default": True,
            "layout": {
                "widgets": [
                    {
                        "id": "soc",
                        "type": "battery-gauge",
                        "vehicle_id": vehicle["id"],
                        "metric": "battery.soc",
                        "x": 0,
                        "y": 0,
                        "w": 3,
                        "h": 2,
                    }
                ]
            },
        },
    )
    assert dashboard.status_code == 201, dashboard.text
    assert client.get("/api/v1/dashboards").json()[0]["layout"]["widgets"][0]["type"] == (
        "battery-gauge"
    )

    empty_dashboard = client.post(
        "/api/v1/dashboards",
        headers={"X-CSRF-Token": csrf},
        json={"name": "Empty workspace", "layout": {"widgets": []}},
    )
    assert empty_dashboard.status_code == 201, empty_dashboard.text
    assert empty_dashboard.json()["layout"] == {"widgets": []}


def test_vehicle_deletion_removes_owned_data_and_unpins_dashboard_widgets(
    registered: tuple[TestClient, str],
) -> None:
    client, csrf = registered
    vehicle, enrolled = _vehicle_and_device(client, csrf)
    credential = enrolled["credential"]
    telemetry = {
        "boot_id": str(uuid4()),
        "samples": [
            {
                "id": str(uuid4()),
                "sequence": 1,
                "recorded_at": datetime.now(UTC).isoformat(),
                "position": None,
                "metrics": {"vehicle.speed": 12},
                "device": {},
            }
        ],
    }
    assert (
        client.post(
            "/api/v1/device/telemetry/batch",
            headers={"Authorization": f"Device {credential}"},
            json=telemetry,
        ).status_code
        == 200
    )
    dashboard = client.post(
        "/api/v1/dashboards",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": "Pinned",
            "layout": {
                "widgets": [
                    {
                        "id": "speed",
                        "type": "metric-card",
                        "vehicle_id": vehicle["id"],
                        "metric": "vehicle.speed",
                        "x": 0,
                        "y": 0,
                        "w": 3,
                        "h": 2,
                    }
                ]
            },
        },
    )
    assert dashboard.status_code == 201
    hook = client.post(
        "/api/v1/hooks",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": "Vehicle-only hook",
            "vehicle_id": vehicle["id"],
            "source": "ctx.log.info('test')",
        },
    )
    assert hook.status_code == 201, hook.text

    deleted = client.delete(f"/api/v1/vehicles/{vehicle['id']}", headers={"X-CSRF-Token": csrf})

    assert deleted.status_code == 204, deleted.text
    assert client.get(f"/api/v1/vehicles/{vehicle['id']}").status_code == 404
    assert client.get("/api/v1/devices").json() == []
    assert client.get("/api/v1/hooks").json() == []
    widgets = client.get("/api/v1/dashboards").json()[0]["layout"]["widgets"]
    assert "vehicle_id" not in widgets[0]
    assert (
        client.post(
            "/api/v1/device/telemetry/batch",
            headers={"Authorization": f"Device {credential}"},
            json=telemetry,
        ).status_code
        == 401
    )
