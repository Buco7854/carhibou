from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient


def _seed(client: TestClient, csrf: str) -> str:
    vehicle = client.post(
        "/api/v1/vehicles", headers={"X-CSRF-Token": csrf}, json={"name": "Table car"}
    ).json()
    token = client.post(
        f"/api/v1/vehicles/{vehicle['id']}/enrollments",
        headers={"X-CSRF-Token": csrf},
        json={"name": "Agent"},
    ).json()["token"]
    credential = client.post(
        "/api/v1/device/enroll",
        json={"token": token, "agent_version": "test", "hostname": "sim"},
    ).json()["credential"]
    base = datetime.now(UTC) - timedelta(minutes=10)
    samples: list[dict[str, Any]] = [
        {
            "id": str(uuid4()),
            "sequence": index,
            "recorded_at": (base + timedelta(minutes=index)).isoformat(),
            "position": {"latitude": 48.0 + index, "longitude": 2.0, "speed": 10.0 * index},
            "metrics": {"battery.soc": soc, "charging.active": index == 0},
            "device": {"mobile_signal": -70 - index},
        }
        for index, soc in enumerate([90, 30, 60])
    ]
    # A profile-specific signal only present on the last row must still become a column.
    last_metrics: dict[str, Any] = samples[-1]["metrics"]
    last_metrics["custom.oil_pressure"] = 3.4
    response = client.post(
        "/api/v1/device/telemetry/batch",
        headers={"Authorization": f"Device {credential}"},
        json={"boot_id": str(uuid4()), "samples": samples},
    )
    assert response.status_code == 200, response.text
    return str(vehicle["id"])


def test_entries_default_to_latest_first_and_expose_every_reported_column(
    registered: tuple[TestClient, str],
) -> None:
    client, csrf = registered
    vehicle_id = _seed(client, csrf)

    body = client.get(f"/api/v1/vehicles/{vehicle_id}/history/entries").json()
    assert body["total"] == 3
    assert [row["metrics"]["battery.soc"] for row in body["entries"]] == [60, 30, 90]
    assert body["metric_keys"] == ["battery.soc", "charging.active", "custom.oil_pressure"]
    assert body["device_keys"] == ["mobile_signal"]
    # A row that never reported the signal simply omits the key.
    assert body["entries"][1]["metrics"].get("custom.oil_pressure") is None


def test_entries_sort_and_filter_on_profile_defined_metrics(
    registered: tuple[TestClient, str],
) -> None:
    client, csrf = registered
    vehicle_id = _seed(client, csrf)
    url = f"/api/v1/vehicles/{vehicle_id}/history/entries"

    ascending = client.get(url, params={"sort": "metric:battery.soc", "direction": "asc"}).json()
    assert [row["metrics"]["battery.soc"] for row in ascending["entries"]] == [30, 60, 90]

    # A filter is "column|minimum|maximum|present"; the column key already contains
    # a colon, so the segments are separated by a pipe.
    ranged = client.get(url, params={"filter": "metric:battery.soc|50||"}).json()
    assert ranged["total"] == 2
    assert all(row["metrics"]["battery.soc"] >= 50 for row in ranged["entries"])

    sparse = client.get(url, params={"filter": "metric:custom.oil_pressure|||1"}).json()
    assert sparse["total"] == 1

    # Several filters narrow the same result set together: only the third row is
    # both above 50% charge and above 15 km/h.
    combined = client.get(
        url, params=[("filter", "metric:battery.soc|50||"), ("filter", "speed|15||")]
    ).json()
    assert combined["total"] == 1
    assert combined["entries"][0]["metrics"]["battery.soc"] == 60

    assert client.get(url, params={"filter": "|50||"}).status_code == 400
    assert client.get(url, params={"filter": "speed|not-a-number||"}).status_code == 400
    assert client.get(url, params={"filter": "drop table|1||"}).status_code == 400

    # Booleans are not numbers, so they sort last instead of breaking the query.
    boolean = client.get(url, params={"sort": "metric:charging.active"}).json()
    assert boolean["total"] == 3
    assert len(boolean["entries"]) == 3

    assert client.get(url, params={"sort": "metric:"}).status_code == 400
    assert client.get(url, params={"sort": "drop table"}).status_code == 400


def test_entries_paginate_and_sort_by_device_and_fixed_columns(
    registered: tuple[TestClient, str],
) -> None:
    client, csrf = registered
    vehicle_id = _seed(client, csrf)
    url = f"/api/v1/vehicles/{vehicle_id}/history/entries"

    page = client.get(url, params={"limit": 2, "offset": 0, "sort": "speed"}).json()
    assert page["total"] == 3
    assert [row["speed"] for row in page["entries"]] == [20.0, 10.0]
    rest = client.get(url, params={"limit": 2, "offset": 2, "sort": "speed"}).json()
    assert [row["speed"] for row in rest["entries"]] == [0.0]

    signal = client.get(url, params={"sort": "device:mobile_signal", "direction": "asc"}).json()
    assert [row["device"]["mobile_signal"] for row in signal["entries"]] == [-72, -71, -70]
