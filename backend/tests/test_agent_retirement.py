"""Removing an agent used to remove everything it had ever reported.

Retiring takes the source out of service and keeps its readings, with their
provenance intact. Purging is the other choice, and has to be asked for.
"""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.telemetry.models import MetricCandidate, Telemetry, TelemetryObservation
from backend.tests.test_normalized_telemetry import _sample, _source, _upload

CSRF = "X-CSRF-Token"


def _retire(client: TestClient, csrf: str, agent_id: str) -> None:
    response = client.delete(f"/api/v1/agents/{agent_id}", headers={CSRF: csrf})
    assert response.status_code == 204, response.text


def _purge(client: TestClient, csrf: str, agent_id: str) -> None:
    response = client.delete(
        f"/api/v1/agents/{agent_id}?purge_telemetry=true", headers={CSRF: csrf}
    )
    assert response.status_code == 204, response.text


def _counts(db: Session, vehicle_id: str) -> tuple[int, int, int]:
    return (
        db.scalar(select(func.count(Telemetry.id)).where(Telemetry.vehicle_id == vehicle_id)) or 0,
        db.scalar(
            select(func.count(TelemetryObservation.id)).where(
                TelemetryObservation.vehicle_id == vehicle_id
            )
        )
        or 0,
        db.scalar(
            select(func.count())
            .select_from(MetricCandidate)
            .where(MetricCandidate.vehicle_id == vehicle_id)
        )
        or 0,
    )


def test_retiring_keeps_every_reading_and_its_provenance(
    registered: tuple[TestClient, str], db_factory: sessionmaker[Session]
) -> None:
    client, csrf = registered
    vehicle_id, agent_id, credential = _source(client, csrf)
    at = datetime.now(UTC) - timedelta(minutes=2)
    _upload(client, credential, [_sample(at, 0, {"battery.soc": 61, "vehicle.odometer": 4200})])

    with db_factory() as db:
        before = _counts(db, vehicle_id)
    assert before[0] and before[1] and before[2], "the upload should have landed"

    _retire(client, csrf, agent_id)

    with db_factory() as db:
        assert _counts(db, vehicle_id) == before, "retiring must not delete anything"

    # The readings still resolve, and still say who reported them.
    state = client.get(f"/api/v1/vehicles/{vehicle_id}").json()["state"]
    soc = state["readings"]["battery.soc"]
    assert soc["value"] == 61
    assert soc["source_id"] == agent_id
    assert soc["source_kind"] == "agent"

    # And history keeps disclosing the source.
    samples = client.get(
        f"/api/v1/vehicles/{vehicle_id}/history/observations",
        params={"start": (at - timedelta(minutes=1)).isoformat()},
    ).json()["samples"]
    assert samples and samples[0]["source_id"] == agent_id
    assert samples[0]["observations"][0]["source_id"] == agent_id


def test_a_retired_agent_leaves_the_active_list(registered: tuple[TestClient, str]) -> None:
    client, csrf = registered
    vehicle_id, agent_id, _credential = _source(client, csrf)
    _source(client, csrf, vehicle_id=vehicle_id, name="Still working")

    assert len(client.get("/api/v1/agents").json()) == 2
    _retire(client, csrf, agent_id)

    remaining = client.get("/api/v1/agents").json()
    assert [row["id"] for row in remaining] != [agent_id]
    assert agent_id not in {row["id"] for row in remaining}
    assert len(remaining) == 1


def test_a_retired_source_cannot_upload_again(registered: tuple[TestClient, str]) -> None:
    """Retirement is permanent, so the hardware must not be able to come back."""
    client, csrf = registered
    _vehicle_id, agent_id, credential = _source(client, csrf)
    _retire(client, csrf, agent_id)

    rejected = client.post(
        "/api/v1/agent/telemetry/batch",
        headers={"Authorization": f"Agent {credential}"},
        json={"boot_id": "11111111-1111-4111-8111-111111111111", "samples": []},
    )
    assert rejected.status_code == 401, rejected.text
    assert (
        client.get(
            "/api/v1/agent/config", headers={"Authorization": f"Agent {credential}"}
        ).status_code
        == 401
    )


def test_a_retired_source_stops_holding_the_vehicle_online(
    registered: tuple[TestClient, str],
) -> None:
    client, csrf = registered
    vehicle_id, agent_id, credential = _source(client, csrf)
    _upload(client, credential, [_sample(datetime.now(UTC), 0, {"battery.soc": 55})])
    assert client.get(f"/api/v1/vehicles/{vehicle_id}").json()["state"]["online"] is True

    _retire(client, csrf, agent_id)
    assert client.get(f"/api/v1/vehicles/{vehicle_id}").json()["state"]["online"] is False


def test_purging_takes_the_telemetry_with_it(
    registered: tuple[TestClient, str], db_factory: sessionmaker[Session]
) -> None:
    client, csrf = registered
    vehicle_id, agent_id, credential = _source(client, csrf)
    _upload(client, credential, [_sample(datetime.now(UTC), 0, {"battery.soc": 61})])
    with db_factory() as db:
        assert _counts(db, vehicle_id) != (0, 0, 0)

    _purge(client, csrf, agent_id)

    with db_factory() as db:
        assert _counts(db, vehicle_id) == (0, 0, 0)
    assert client.get("/api/v1/agents").json() == []
    assert client.get("/api/v1/agents/retired").json() == []


def test_retired_source_accounting_counts_what_each_one_holds(
    registered: tuple[TestClient, str],
) -> None:
    client, csrf = registered
    vehicle_id, agent_id, credential = _source(client, csrf, name="Retired one")
    oldest = datetime.now(UTC) - timedelta(hours=3)
    newest = datetime.now(UTC) - timedelta(minutes=5)
    _upload(
        client,
        credential,
        [
            _sample(oldest, 0, {"battery.soc": 40}),
            _sample(newest, 1, {"battery.soc": 44}),
        ],
    )
    # A second source that never reported, retired as well.
    _vehicle, silent_id, _silent_credential = _source(
        client, csrf, vehicle_id=vehicle_id, name="Never reported"
    )
    # And one still in service, which must not be counted.
    _source(client, csrf, vehicle_id=vehicle_id, name="Working")

    assert client.get("/api/v1/agents/retired").json() == []
    _retire(client, csrf, agent_id)
    _retire(client, csrf, silent_id)

    rows = {row["source_id"]: row for row in client.get("/api/v1/agents/retired").json()}
    assert set(rows) == {agent_id, silent_id}

    reported = rows[agent_id]
    assert reported["name"] == "Retired one"
    assert reported["samples"] == 2
    assert reported["retired_at"] is not None
    assert datetime.fromisoformat(reported["oldest"]) == oldest
    assert datetime.fromisoformat(reported["newest"]) == newest

    # A source that reported nothing is still orphaned, and says so with zero.
    assert rows[silent_id]["samples"] == 0
    assert rows[silent_id]["oldest"] is None
    assert rows[silent_id]["newest"] is None


def test_the_retired_listing_is_admin_only(registered: tuple[TestClient, str]) -> None:
    client, _csrf = registered
    assert client.get("/api/v1/agents/retired").status_code == 200
    fresh = TestClient(client.app)
    assert fresh.get("/api/v1/agents/retired").status_code == 401
