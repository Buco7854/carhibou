from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

from fastapi.testclient import TestClient


def _source(
    client: TestClient, csrf: str, *, capacity: float | None = None
) -> tuple[dict[str, Any], str]:
    payload: dict[str, object] = {"name": "Segment vehicle"}
    if capacity is not None:
        payload["battery_nominal_capacity_kwh"] = capacity
    vehicle = client.post("/api/v1/vehicles", headers={"X-CSRF-Token": csrf}, json=payload).json()
    enrollment = client.post(
        f"/api/v1/vehicles/{vehicle['id']}/enrollments",
        headers={"X-CSRF-Token": csrf},
        json={"implementation_id": "custom", "name": "Segment source"},
    ).json()
    enrolled = client.post(
        "/api/v1/agent/enroll",
        json={
            "token": enrollment["token"],
            "implementation_id": "custom",
            "protocol_version": 1,
            "agent_version": "test",
            "hostname": "segments",
        },
    ).json()
    return vehicle, enrolled["credential"]


def _upload(
    client: TestClient,
    credential: str,
    base: datetime,
    samples: list[tuple[int, dict[str, object], tuple[float, float, float | None] | None]],
) -> None:
    response = client.post(
        "/api/v1/agent/telemetry/batch",
        headers={"Authorization": f"Agent {credential}"},
        json={
            "boot_id": str(uuid4()),
            "samples": [
                {
                    "id": str(uuid4()),
                    "sequence": sequence,
                    "recorded_at": (base + timedelta(seconds=seconds)).isoformat(),
                    "metrics": metrics,
                    "position": (
                        {
                            "latitude": position[0],
                            "longitude": position[1],
                            "speed": position[2],
                        }
                        if position
                        else None
                    ),
                }
                for sequence, (seconds, metrics, position) in enumerate(samples)
            ],
        },
    )
    assert response.status_code == 200, response.text


def _segments(
    client: TestClient, vehicle_id: str, start: datetime, end: datetime
) -> dict[str, Any]:
    response = client.get(
        f"/api/v1/vehicles/{vehicle_id}/segments",
        params={"start": start.isoformat(), "end": end.isoformat()},
    )
    assert response.status_code == 200, response.text
    return cast(dict[str, Any], response.json())


def test_segments_join_gaps_and_derive_drive_and_charge_statistics(
    registered: tuple[TestClient, str],
) -> None:
    client, csrf = registered
    vehicle, credential = _source(client, csrf, capacity=60)
    base = datetime.now(UTC) - timedelta(hours=2)
    _upload(
        client,
        credential,
        base,
        [
            (
                0,
                {"vehicle.in_use": True, "vehicle.odometer": 100, "battery.soc": 80},
                (48.0, 2.0, 20),
            ),
            (
                70,
                {"vehicle.in_use": True, "vehicle.odometer": 101, "battery.soc": 79},
                (48.01, 2.01, 30),
            ),
            (
                200,
                {"vehicle.in_use": True, "vehicle.odometer": 102, "battery.soc": 78},
                (48.02, 2.02, 50),
            ),
            (
                400,
                {"vehicle.in_use": True},
                None,
            ),
            (
                450,
                {"vehicle.in_use": True},
                None,
            ),
            (
                700,
                {"vehicle.in_use": False, "charging.active": False},
                (49.0, 3.0, 90),
            ),
            (
                1000,
                {
                    "vehicle.in_use": False,
                    "charging.active": True,
                    "charging.power": 6,
                    "battery.soc": 20,
                    "teslamate.charge_energy_added": 1,
                },
                (49.1, 3.1, 0),
            ),
            (
                1060,
                {
                    "vehicle.in_use": False,
                    "charging.active": True,
                    "charging.power": 12,
                    "battery.soc": 25,
                    "teslamate.charge_energy_added": 2,
                },
                (49.1, 3.1, 0),
            ),
            (
                1120,
                {
                    "vehicle.in_use": False,
                    "charging.active": True,
                    "charging.power": 6,
                    "battery.soc": 30,
                    "teslamate.charge_energy_added": 3,
                },
                (49.1, 3.1, 0),
            ),
            (1400, {"charging.active": True, "charging.power": 3}, None),
            (1460, {"charging.active": True, "charging.power": 5}, None),
        ],
    )
    result = _segments(
        client, vehicle["id"], base - timedelta(seconds=1), base + timedelta(hours=1)
    )
    assert len(result["drives"]) == 1
    drive = result["drives"][0]
    assert drive["duration_seconds"] == 200
    assert drive["distance_km"] == 2
    assert drive["avg_speed"] == 100 / 3
    assert drive["max_speed"] == 50
    assert drive["soc_start"] == 80
    assert drive["soc_end"] == 78
    assert drive["energy_kwh"] == 1.2
    assert drive["start_position"] == {"latitude": 48.0, "longitude": 2.0}
    assert drive["end_position"] == {"latitude": 48.02, "longitude": 2.02}

    assert len(result["charges"]) == 2
    charge, integrated_charge = result["charges"]
    assert charge["duration_seconds"] == 120
    assert charge["soc_start"] == 20
    assert charge["soc_end"] == 30
    assert charge["energy_kwh"] == 2
    assert charge["peak_power"] == 12
    assert charge["avg_power"] == 9
    assert charge["position"] == {"latitude": 49.1, "longitude": 3.1}
    assert integrated_charge["energy_kwh"] == 4 / 60
    assert integrated_charge["peak_power"] == 5
    assert integrated_charge["avg_power"] == 4


def test_drive_precedence_movement_fallback_and_exact_gap_boundary(
    registered: tuple[TestClient, str],
) -> None:
    client, csrf = registered
    vehicle, credential = _source(client, csrf)
    base = datetime.now(UTC) - timedelta(hours=1)
    _upload(
        client,
        credential,
        base,
        [
            (0, {"vehicle.in_use": False, "charging.active": False}, (48.0, 2.0, 40)),
            (10, {"charging.active": False}, (48.01, 2.01, 0)),
            (80, {"charging.active": False}, (48.02, 2.02, 0)),
            (300, {"vehicle.state": "ready"}, None),
            (480, {"vehicle.state": "ready"}, None),
        ],
    )
    result = _segments(
        client, vehicle["id"], base - timedelta(seconds=1), base + timedelta(hours=1)
    )
    assert len(result["drives"]) == 1
    assert result["drives"][0]["duration_seconds"] == 70
    assert result["drives"][0]["distance_km"] > 1


def test_segments_omit_missing_values_and_enforce_range_boundaries(
    registered: tuple[TestClient, str],
) -> None:
    client, csrf = registered
    vehicle, credential = _source(client, csrf)
    base = datetime.now(UTC) - timedelta(hours=1)
    _upload(
        client,
        credential,
        base,
        [
            (0, {"vehicle.in_use": True}, None),
            (60, {"vehicle.in_use": True}, None),
            (300, {"charging.active": True}, None),
        ],
    )
    result = _segments(client, vehicle["id"], base, base + timedelta(hours=1))
    drive = result["drives"][0]
    assert set(drive) == {"start", "end", "duration_seconds"}
    charge = result["charges"][0]
    assert set(charge) == {"start", "end", "duration_seconds"}

    endpoint = f"/api/v1/vehicles/{vehicle['id']}/segments"
    assert client.get(endpoint).status_code == 422
    assert (
        client.get(
            endpoint,
            params={
                "start": base.isoformat(),
                "end": (base + timedelta(days=92, seconds=1)).isoformat(),
            },
        ).status_code
        == 400
    )
    assert (
        client.get(
            endpoint,
            params={"start": base.isoformat(), "end": (base + timedelta(days=92)).isoformat()},
        ).status_code
        == 200
    )
    assert (
        client.get(
            endpoint,
            params={"start": base.isoformat(), "end": base.isoformat()},
        ).status_code
        == 400
    )
