"""A connector is a source like any other, so it retires like one.

The lifecycle is the agent's, reached through the shadow agent a connector
reports as; only the effects on the connector row itself are local.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.agents.models import Agent
from backend.app.connectors.models import Connector
from backend.app.connectors.runtime import ConnectorSupervisor
from backend.app.telemetry.models import Telemetry, TelemetryObservation
from backend.app.telemetry.schemas import TelemetryBatch
from backend.app.telemetry.services import RetiredSourceError, ingest_batch
from backend.tests.test_normalized_telemetry import _sample

CSRF = "X-CSRF-Token"
CONFIG = {"host": "broker.example.com", "namespace": "fleet", "sample_seconds": 10}


def _connector(client: TestClient, csrf: str) -> tuple[str, str]:
    vehicle = client.post("/api/v1/vehicles", headers={CSRF: csrf}, json={"name": "Wired car"})
    assert vehicle.status_code == 201, vehicle.text
    vehicle_id = vehicle.json()["id"]
    created = client.post(
        f"/api/v1/vehicles/{vehicle_id}/connectors",
        headers={CSRF: csrf},
        json={"kind": "teslamate.mqtt", "name": "Broker", "config": CONFIG},
    )
    assert created.status_code == 201, created.text
    return vehicle_id, created.json()["id"]


def _report(db: Session, connector_id: str, at: datetime) -> None:
    """Ingest the way the connector runtime does: straight in, no credential."""
    agent = db.get(Agent, connector_id)
    assert agent is not None
    ingest_batch(
        db,
        agent,
        TelemetryBatch.model_validate(
            {
                "boot_id": "22222222-2222-4222-8222-222222222222",
                "samples": [_sample(at, 0, {"battery.soc": 58})],
            }
        ),
    )
    db.commit()


def _retire(client: TestClient, csrf: str, connector_id: str) -> None:
    response = client.delete(f"/api/v1/connectors/{connector_id}", headers={CSRF: csrf})
    assert response.status_code == 204, response.text


def test_retiring_a_connector_keeps_its_readings_and_their_provenance(
    registered: tuple[TestClient, str], db_factory: sessionmaker[Session]
) -> None:
    client, csrf = registered
    vehicle_id, connector_id = _connector(client, csrf)
    at = datetime.now(UTC) - timedelta(minutes=1)
    with db_factory() as db:
        _report(db, connector_id, at)

    _retire(client, csrf, connector_id)

    with db_factory() as db:
        assert db.scalar(select(func.count(Telemetry.id))) == 1
        assert db.scalar(select(func.count(TelemetryObservation.id))) == 1

    reading = client.get(f"/api/v1/vehicles/{vehicle_id}").json()["state"]["readings"]
    assert reading["battery.soc"]["source_id"] == connector_id
    assert reading["battery.soc"]["source_kind"] == "connector"


def test_a_retired_connector_leaves_the_active_list_and_cannot_be_changed(
    registered: tuple[TestClient, str],
) -> None:
    client, csrf = registered
    _vehicle_id, connector_id = _connector(client, csrf)
    assert len(client.get("/api/v1/connectors").json()) == 1

    _retire(client, csrf, connector_id)
    assert client.get("/api/v1/connectors").json() == []

    revived = client.put(
        f"/api/v1/connectors/{connector_id}",
        headers={CSRF: csrf},
        json={"name": "Broker", "enabled": True, "config": CONFIG},
    )
    assert revived.status_code == 400, revived.text
    assert "retired" in revived.json()["error"]["message"]


def test_a_retired_connector_stops_running_and_cannot_report(
    registered: tuple[TestClient, str], db_factory: sessionmaker[Session]
) -> None:
    """The supervisor drops it, and the ingestion path refuses it even if a
    session were still in flight. A connector never authenticates, so this guard
    is where its retirement is enforced."""
    client, csrf = registered
    _vehicle_id, connector_id = _connector(client, csrf)

    supervisor = ConnectorSupervisor(db_factory)
    assert connector_id in supervisor._definitions()

    _retire(client, csrf, connector_id)
    assert supervisor._definitions() == {}

    with db_factory() as db, pytest.raises(RetiredSourceError):
        _report(db, connector_id, datetime.now(UTC))


def test_a_retired_connector_appears_in_the_retired_source_accounting(
    registered: tuple[TestClient, str], db_factory: sessionmaker[Session]
) -> None:
    client, csrf = registered
    _vehicle_id, connector_id = _connector(client, csrf)
    at = datetime.now(UTC) - timedelta(minutes=2)
    with db_factory() as db:
        _report(db, connector_id, at)

    assert client.get("/api/v1/agents/retired").json() == []
    _retire(client, csrf, connector_id)

    rows = client.get("/api/v1/agents/retired").json()
    assert len(rows) == 1
    row = rows[0]
    assert row["source_id"] == connector_id
    assert row["source_kind"] == "connector"
    assert row["name"] == "Broker"
    assert row["samples"] == 1
    assert datetime.fromisoformat(row["oldest"]) == at


def test_purging_a_connector_takes_everything_it_collected(
    registered: tuple[TestClient, str], db_factory: sessionmaker[Session]
) -> None:
    client, csrf = registered
    _vehicle_id, connector_id = _connector(client, csrf)
    with db_factory() as db:
        _report(db, connector_id, datetime.now(UTC))

    purged = client.delete(
        f"/api/v1/connectors/{connector_id}?purge_telemetry=true", headers={CSRF: csrf}
    )
    assert purged.status_code == 204, purged.text

    with db_factory() as db:
        assert db.get(Connector, connector_id) is None
        assert db.get(Agent, connector_id) is None
        assert db.scalar(select(func.count(Telemetry.id))) == 0
        assert db.scalar(select(func.count(TelemetryObservation.id))) == 0
    assert client.get("/api/v1/agents/retired").json() == []


def test_a_retired_connector_can_still_be_purged_afterwards(
    registered: tuple[TestClient, str], db_factory: sessionmaker[Session]
) -> None:
    """Retiring first and purging later is the ordinary path: the accounting is
    what somebody reads before deciding."""
    client, csrf = registered
    _vehicle_id, connector_id = _connector(client, csrf)
    with db_factory() as db:
        _report(db, connector_id, datetime.now(UTC))
    _retire(client, csrf, connector_id)

    purged = client.delete(
        f"/api/v1/connectors/{connector_id}?purge_telemetry=true", headers={CSRF: csrf}
    )
    assert purged.status_code == 204, purged.text
    with db_factory() as db:
        assert db.scalar(select(func.count(Telemetry.id))) == 0
