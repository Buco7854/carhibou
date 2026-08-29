from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.history.segments import (
    _charge_evidence,
    _charge_segment,
    _distance_km,
    _drive_segment,
    _power_integral,
)
from backend.app.telemetry.models import (
    Telemetry,
    TelemetryObservation,
    TelemetryPositionObservation,
)


def _row(
    base: datetime,
    seconds: int,
    *,
    sequence: int = 0,
    metrics: dict[str, object] | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> Telemetry:
    telemetry_id = str(uuid4())
    observed_at = base + timedelta(seconds=seconds)
    return Telemetry(
        id=telemetry_id,
        vehicle_id="vehicle",
        agent_id="agent",
        boot_id="boot",
        sequence=sequence,
        recorded_at=observed_at,
        reporting_interval=None,
        event_driven=False,
        agent_data={},
        observation_rows=[
            TelemetryObservation(
                telemetry_id=telemetry_id,
                vehicle_id="vehicle",
                source_id="agent",
                metric_key=key,
                value=value,
                observed_at=observed_at,
                channel="can",
                method="direct",
            )
            for key, value in (metrics or {}).items()
        ],
        position_observation=(
            TelemetryPositionObservation(
                telemetry_id=telemetry_id,
                vehicle_id="vehicle",
                source_id="agent",
                value={"latitude": latitude, "longitude": longitude},
                observed_at=observed_at,
                channel="gnss",
                method="direct",
            )
            if latitude is not None and longitude is not None
            else None
        ),
    )


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
            "protocol_version": 2,
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
                _sample_payload(base, sequence, seconds, metrics, position)
                for sequence, (seconds, metrics, position) in enumerate(samples)
            ],
        },
    )
    assert response.status_code == 200, response.text


def _sample_payload(
    base: datetime,
    sequence: int,
    seconds: int,
    metrics: dict[str, object],
    position: tuple[float, float, float | None] | None,
) -> dict[str, object]:
    observed_at = (base + timedelta(seconds=seconds)).isoformat()
    return {
        "id": str(uuid4()),
        "sequence": sequence,
        "recorded_at": observed_at,
        "observations": [
            {
                "key": key,
                "value": value,
                "observed_at": observed_at,
                "channel": "can",
                "method": "direct",
            }
            for key, value in metrics.items()
        ],
        "position": (
            {
                "value": {
                    "latitude": position[0],
                    "longitude": position[1],
                    "speed": position[2],
                },
                "observed_at": observed_at,
                "channel": "gnss",
                "method": "direct",
            }
            if position
            else None
        ),
    }


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
                    "charging.energy_added": 1,
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
                    "charging.energy_added": 2,
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
                    "charging.energy_added": 3,
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
    assert charge["avg_power"] == pytest.approx(9)
    assert charge["position"] == {"latitude": 49.1, "longitude": 3.1}
    assert integrated_charge["energy_kwh"] == 3 / 60
    assert integrated_charge["peak_power"] == 5
    assert integrated_charge["avg_power"] == 3


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
            (360, {"charging.active": True}, None),
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


def test_sparse_charge_power_uses_zero_order_hold() -> None:
    base = datetime.now(UTC)
    rows = [
        _row(base, 0, metrics={"charging.power": 11}),
        _row(base, 600, metrics={"battery.soc": 55}),
        _row(base, 1200, metrics={"battery.soc": 60}),
        _row(base, 1800, metrics={"charging.power": 11}),
    ]

    assert _power_integral(rows) == (5.5, 11)


@pytest.mark.parametrize(
    ("metrics", "expected"),
    [
        ({"charging.power": 0.2}, False),
        ({"charging.power": 0.499999}, False),
        ({"charging.power": 0.5}, True),
        ({"charging.active": True, "charging.power": 0}, True),
    ],
)
def test_charge_evidence_applies_the_half_kilowatt_floor(
    metrics: dict[str, object], expected: bool
) -> None:
    assert _charge_evidence(_row(datetime.now(UTC), 0, metrics=metrics)) is expected


def test_distance_falls_back_to_gps_with_only_one_odometer_sample() -> None:
    base = datetime.now(UTC)
    rows = [
        _row(
            base,
            0,
            metrics={"vehicle.odometer": 1000},
            latitude=48.0,
            longitude=2.0,
        ),
        _row(base, 60, latitude=48.1, longitude=2.0),
        _row(base, 120, latitude=48.2, longitude=2.0),
    ]

    assert _distance_km(rows) == pytest.approx(22.239, rel=1e-3)


def test_segments_require_minimum_duration_and_two_soc_samples() -> None:
    base = datetime.now(UTC)
    one_charge = [_row(base, 0, metrics={"charging.power": 7})]
    assert _charge_segment(one_charge) is None

    drive = _drive_segment(
        [
            _row(base, 0, metrics={"battery.soc": 80}),
            _row(base, 60),
        ],
        50,
    )
    assert drive is not None
    assert drive.soc_start is None
    assert drive.soc_end is None
    assert drive.energy_kwh is None


def test_segments_order_equal_timestamps_by_sequence(
    registered: tuple[TestClient, str],
) -> None:
    client, csrf = registered
    vehicle, credential = _source(client, csrf)
    base = datetime.now(UTC) - timedelta(hours=1)
    response = client.post(
        "/api/v1/agent/telemetry/batch",
        headers={"Authorization": f"Agent {credential}"},
        json={
            "boot_id": str(uuid4()),
            "samples": [
                {
                    **_sample_payload(
                        base,
                        0,
                        0,
                        {
                            "charging.active": True,
                            "charging.energy_added": 0,
                            "battery.soc": 10,
                        },
                        None,
                    ),
                    "id": "ffffffff-ffff-4fff-8fff-ffffffffffff",
                },
                {
                    **_sample_payload(
                        base,
                        1,
                        0,
                        {
                            "charging.active": True,
                            "charging.energy_added": 1,
                            "battery.soc": 11,
                        },
                        None,
                    ),
                    "id": "00000000-0000-4000-8000-000000000000",
                },
                {
                    **_sample_payload(
                        base,
                        2,
                        60,
                        {
                            "charging.active": True,
                            "charging.energy_added": 2,
                            "battery.soc": 12,
                        },
                        None,
                    ),
                    "id": "11111111-1111-4111-8111-111111111111",
                },
            ],
        },
    )
    assert response.status_code == 200, response.text

    charge = _segments(client, vehicle["id"], base, base + timedelta(seconds=61))["charges"][0]
    assert charge["soc_start"] == 10
    assert charge["energy_kwh"] == 2


def test_segments_range_is_start_inclusive_and_end_exclusive(
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
            (120, {"vehicle.in_use": True}, None),
            (180, {"vehicle.in_use": True}, None),
        ],
    )

    first = _segments(client, vehicle["id"], base, base + timedelta(seconds=120))["drives"]
    second = _segments(
        client,
        vehicle["id"],
        base + timedelta(seconds=120),
        base + timedelta(seconds=181),
    )["drives"]
    assert len(first) == len(second) == 1
    assert first[0]["duration_seconds"] == second[0]["duration_seconds"] == 60
    assert datetime.fromisoformat(first[0]["end"]) == base + timedelta(seconds=60)
    assert datetime.fromisoformat(second[0]["start"]) == base + timedelta(seconds=120)
