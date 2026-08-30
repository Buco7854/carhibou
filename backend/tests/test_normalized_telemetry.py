from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.telemetry.contacts import latest_contact_periods
from backend.app.telemetry.models import (
    MetricCandidate,
    SourceContactPeriod,
    Telemetry,
    TelemetryObservation,
)
from backend.app.telemetry.resolution import Candidate, resolve_readings, vehicle_source_online
from backend.app.telemetry.schemas import TelemetryBatch
from backend.app.telemetry.services import touch_source_contact
from backend.app.vehicle_state.models import VehicleState


def _source(
    client: TestClient, csrf: str, vehicle_id: str | None = None, name: str = "Source"
) -> tuple[str, str, str]:
    headers = {"X-CSRF-Token": csrf}
    if vehicle_id is None:
        vehicle = client.post("/api/v1/vehicles", headers=headers, json={"name": "V2 car"})
        assert vehicle.status_code == 201, vehicle.text
        vehicle_id = vehicle.json()["id"]
    enrollment = client.post(
        f"/api/v1/vehicles/{vehicle_id}/enrollments",
        headers=headers,
        json={"implementation_id": "custom", "name": name},
    )
    assert enrollment.status_code == 201, enrollment.text
    enrolled = client.post(
        "/api/v1/agent/enroll",
        json={
            "token": enrollment.json()["token"],
            "implementation_id": "custom",
            "protocol_version": 2,
            "agent_version": "test",
            "hostname": name,
        },
    )
    assert enrolled.status_code == 201, enrolled.text
    return vehicle_id, enrolled.json()["agent_id"], enrolled.json()["credential"]


def _sample(
    at: datetime,
    sequence: int,
    values: dict[str, Any],
    *,
    channel: str = "can",
    position_speed: float | None = None,
    reporting_interval: int | None = 60,
) -> dict[str, Any]:
    stamp = at.isoformat()
    sample: dict[str, Any] = {
        "id": str(uuid4()),
        "sequence": sequence,
        "recorded_at": stamp,
        "observations": [
            {
                "key": key,
                "value": value,
                "observed_at": stamp,
                "channel": channel,
                "method": "direct",
            }
            for key, value in values.items()
        ],
        "agent": {},
    }
    if reporting_interval is not None:
        sample["reporting_interval"] = reporting_interval
    if position_speed is not None:
        sample["position"] = {
            "value": {"latitude": 48.0, "longitude": 2.0, "speed": position_speed},
            "observed_at": stamp,
            "channel": "gnss",
            "method": "direct",
        }
    return sample


def _upload(client: TestClient, credential: str, samples: list[dict[str, Any]]) -> None:
    response = client.post(
        "/api/v1/agent/telemetry/batch",
        headers={"Authorization": f"Agent {credential}"},
        json={"boot_id": str(uuid4()), "samples": samples},
    )
    assert response.status_code == 200, response.text


def test_v2_wire_rejects_the_discarded_parallel_metrics_shape() -> None:
    at = datetime.now(UTC)
    with pytest.raises(ValueError):
        TelemetryBatch.model_validate(
            {
                "boot_id": str(uuid4()),
                "samples": [
                    {
                        "id": str(uuid4()),
                        "sequence": 1,
                        "recorded_at": at.isoformat(),
                        "metrics": {"battery.soc": 50},
                    }
                ],
            }
        )

    duplicate_id = str(uuid4())
    sample = _sample(at, 1, {"battery.soc": 50})
    sample["id"] = duplicate_id
    with pytest.raises(ValueError, match="sample IDs must be unique"):
        TelemetryBatch.model_validate(
            {
                "boot_id": str(uuid4()),
                "samples": [sample, {**sample, "sequence": 2}],
            }
        )


def test_delayed_samples_update_only_their_exact_candidate(
    registered: tuple[TestClient, str], db_factory: sessionmaker[Session]
) -> None:
    client, csrf = registered
    vehicle_id, agent_id, credential = _source(client, csrf)
    base = datetime.now(UTC) - timedelta(minutes=1)
    _upload(client, credential, [_sample(base + timedelta(seconds=20), 2, {"vehicle.speed": 30})])
    _upload(client, credential, [_sample(base + timedelta(seconds=10), 1, {"battery.soc": 60})])
    _upload(client, credential, [_sample(base + timedelta(seconds=5), 0, {"battery.soc": 10})])

    with db_factory() as db:
        speed = db.get(MetricCandidate, (vehicle_id, agent_id, "can", "vehicle.speed"))
        soc = db.get(MetricCandidate, (vehicle_id, agent_id, "can", "battery.soc"))
        assert speed and speed.value == 30
        assert soc and soc.value == 60
    state = client.get(f"/api/v1/vehicles/{vehicle_id}").json()["state"]
    assert state["readings"]["vehicle.speed"]["value"] == 30
    assert state["readings"]["battery.soc"]["value"] == 60


def test_multi_source_resolution_and_explicit_retraction(
    registered: tuple[TestClient, str],
) -> None:
    client, csrf = registered
    vehicle_id, _first_id, first = _source(client, csrf, name="CAN")
    _vehicle_id, _second_id, second = _source(client, csrf, vehicle_id, "GNSS")
    base = datetime.now(UTC) - timedelta(seconds=10)
    _upload(client, first, [_sample(base, 0, {"vehicle.speed": 44})])
    _upload(client, second, [_sample(base + timedelta(seconds=1), 0, {}, position_speed=47)])

    state = client.get(f"/api/v1/vehicles/{vehicle_id}").json()["state"]
    assert state["readings"]["vehicle.speed"]["value"] == 44
    assert state["readings"]["vehicle.speed"]["channel"] == "can"

    _upload(client, first, [_sample(base + timedelta(seconds=2), 1, {"vehicle.speed": None})])
    state = client.get(f"/api/v1/vehicles/{vehicle_id}").json()["state"]
    assert state["readings"]["vehicle.speed"]["value"] == 47
    assert state["readings"]["vehicle.speed"]["channel"] == "gnss"


def test_cadence_and_event_contact_control_freshness() -> None:
    now = datetime.now(UTC)
    sampled = Candidate(
        key="vehicle.speed",
        value=30,
        observed_at=now - timedelta(minutes=10),
        source_id="sampled",
        source_kind="agent",
        channel="can",
        method="direct",
        reporting_interval=300,
    )
    assert resolve_readings([sampled], now)["vehicle.speed"]["fresh"] is True
    assert "vehicle.speed" not in resolve_readings([sampled], now + timedelta(minutes=6))

    event_state = Candidate(
        key="battery.soc",
        value=70,
        observed_at=now - timedelta(days=1),
        source_id="mqtt",
        source_kind="connector",
        channel="mqtt",
        method="direct",
        event_driven=True,
        source_last_contact_at=now,
        source_liveness_window_seconds=15,
    )
    current = resolve_readings([event_state], now)
    assert current["battery.soc"]["fresh"] is True
    expired = resolve_readings([event_state], now + timedelta(minutes=16))
    assert expired["battery.soc"]["fresh"] is False


def test_latest_contact_period_is_the_only_current_contact(
    registered: tuple[TestClient, str], db_factory: sessionmaker[Session]
) -> None:
    client, csrf = registered
    vehicle_id, agent_id, _credential = _source(client, csrf)
    first = datetime.now(UTC) - timedelta(hours=1)
    latest = datetime.now(UTC)
    with db_factory() as db:
        touch_source_contact(db, agent_id, first, 15)
        db.flush()
        touch_source_contact(db, agent_id, latest, 30)
        db.commit()

    with db_factory() as db:
        periods = list(
            db.scalars(
                select(SourceContactPeriod)
                .where(SourceContactPeriod.source_id == agent_id)
                .order_by(SourceContactPeriod.started_at)
            )
        )
        assert len(periods) == 2
        assert latest_contact_periods(db, {agent_id})[agent_id].id == periods[1].id
        assert (
            latest_contact_periods(db, {agent_id}, at=first + timedelta(seconds=10))[agent_id].id
            == periods[0].id
        )
        assert vehicle_source_online(db, vehicle_id, 10, now=latest + timedelta(seconds=89))
        assert not vehicle_source_online(db, vehicle_id, 10, now=latest + timedelta(seconds=91))


def test_charging_resolution_is_explicit_first_and_synthesizes_rate() -> None:
    now = datetime.now(UTC)
    power = Candidate(
        key="battery.power",
        value=-3.4,
        observed_at=now,
        source_id="can-agent",
        source_kind="agent",
        channel="can",
        method="direct",
    )
    resolved = resolve_readings([power], now)
    assert resolved["charging.active"]["value"] is True
    assert resolved["charging.power"]["value"] == 3.4
    assert resolved["charging.power"]["channel"] == "derived"

    explicit = Candidate(
        key="charging.active",
        value=False,
        observed_at=now,
        source_id="can-agent",
        source_kind="agent",
        channel="can",
        method="direct",
    )
    resolved = resolve_readings([power, explicit], now)
    assert resolved["charging.active"]["value"] is False
    assert "charging.power" not in resolved


def test_measured_charging_power_beats_the_resolvers_own_derivation() -> None:
    """A profile that computes AC-side power from volts times amps reports a real
    observation; the resolver's own figure is an inference from pack power. When
    both exist the measured one wins, and it wins as a CAN reading rather than
    being relabelled derived."""
    now = datetime.now(UTC)
    # What the C-Zero profile's computed metric actually produces: a CAN-channel
    # candidate whose method is derived because the profile multiplied two
    # signals, not because the server guessed.
    measured = Candidate(
        key="charging.power",
        value=3.22,
        observed_at=now,
        source_id="can-agent",
        source_kind="agent",
        channel="can",
        method="derived",
    )
    pack = Candidate(
        key="battery.power",
        value=-3.4,
        observed_at=now,
        source_id="can-agent",
        source_kind="agent",
        channel="can",
        method="direct",
    )

    resolved = resolve_readings([measured, pack], now)
    assert resolved["charging.power"]["value"] == 3.22
    assert resolved["charging.power"]["channel"] == "can"
    # The pack-power evidence still answers whether charging is happening.
    assert resolved["charging.active"]["value"] is True

    # Without the measured candidate the derivation is still there for vehicles
    # whose profiles cannot compute it.
    fallback = resolve_readings([pack], now)
    assert fallback["charging.power"]["value"] == 3.4
    assert fallback["charging.power"]["channel"] == "derived"

    # And a measured value that has aged out gives way rather than being kept:
    # charging.power is not a retained metric.
    stale = Candidate(
        key="charging.power",
        value=3.22,
        observed_at=now - timedelta(hours=1),
        source_id="can-agent",
        source_kind="agent",
        channel="can",
        method="derived",
    )
    aged = resolve_readings([stale, pack], now)
    assert aged["charging.power"]["value"] == 3.4
    assert aged["charging.power"]["channel"] == "derived"


def test_history_table_forward_fills_true_observation_times_without_dense_rows(
    registered: tuple[TestClient, str],
) -> None:
    client, csrf = registered
    vehicle_id, _agent_id, credential = _source(client, csrf)
    base = datetime.now(UTC) - timedelta(minutes=5)
    _upload(
        client,
        credential,
        [
            _sample(base, 0, {"battery.soc": 50}),
            _sample(base + timedelta(minutes=2), 1, {"vehicle.speed": 20}),
        ],
    )
    raw = client.get(
        f"/api/v1/vehicles/{vehicle_id}/history/observations",
        params={
            "start": (base - timedelta(seconds=1)).isoformat(),
            "end": (base + timedelta(minutes=4)).isoformat(),
        },
    )
    assert raw.status_code == 200, raw.text
    assert [len(sample["observations"]) for sample in raw.json()["samples"]] == [1, 1]

    table = client.get(
        f"/api/v1/vehicles/{vehicle_id}/history/table",
        params={
            "start": (base - timedelta(seconds=1)).isoformat(),
            "end": (base + timedelta(minutes=4)).isoformat(),
            "step_seconds": 60,
        },
    )
    assert table.status_code == 200, table.text
    rows = table.json()["rows"]
    combined = next(row for row in rows if "vehicle.speed" in row["readings"])
    assert combined["readings"]["battery.soc"]["value"] == 50
    assert (
        datetime.fromisoformat(
            combined["readings"]["battery.soc"]["observed_at"].replace("Z", "+00:00")
        )
        == base
    )
    assert len(rows) < 5
    # Two samples went in, so exactly two reports are spread across the rows.
    assert sum(row["reports"] for row in rows) == 2
    assert combined["reports"] >= 1


def test_history_table_counts_reports_per_row_and_sums_them_when_rows_collapse(
    registered: tuple[TestClient, str],
) -> None:
    """A row exists either because something was reported or because something
    expired at a moment nothing was. Reading that back off observation times
    misreads a report whose values had all already aged out, so the count of
    deliveries inside each row is carried explicitly."""
    client, csrf = registered
    vehicle_id, _agent_id, credential = _source(client, csrf)
    base = datetime.now(UTC) - timedelta(minutes=40)
    # One report that says something, then three parked heartbeats that say
    # nothing: the state they leave behind is identical, so their buckets
    # collapse and the count is what distinguishes the span from silence.
    _upload(
        client,
        credential,
        [
            _sample(base, 0, {"battery.soc": 50}),
            _sample(base + timedelta(minutes=1), 1, {}),
            _sample(base + timedelta(minutes=2), 2, {}),
            _sample(base + timedelta(minutes=3), 3, {}),
        ],
    )

    table = client.get(
        f"/api/v1/vehicles/{vehicle_id}/history/table",
        params={
            "start": (base - timedelta(seconds=1)).isoformat(),
            "end": (base + timedelta(minutes=35)).isoformat(),
            "step_seconds": 60,
        },
    )
    assert table.status_code == 200, table.text
    rows = table.json()["rows"]

    # Every delivery is accounted for exactly once across the whole table.
    assert sum(row["reports"] for row in rows) == 4

    # The collapsed span carries the sum of what merged into it rather than the
    # count of the bucket that happened to open it.
    reporting = [row for row in rows if row["reports"] > 0]
    assert len(reporting) == 1
    assert reporting[0]["reports"] == 4
    assert reporting[0]["collapsed_buckets"] > 1

    # Quiet rows exist because a candidate expired or the range has an edge, and
    # they say so with a zero rather than leaving it to be inferred.
    quiet = [row for row in rows if row["reports"] == 0]
    assert quiet, "expected at least one row born of expiry or the range edge"
    assert all(row["readings"] or row["position"] is None for row in quiet)


def test_history_table_counts_a_report_whose_values_have_all_expired(
    registered: tuple[TestClient, str],
) -> None:
    """The case that defeats inference: a delivery arrives, and by the end of
    its own bucket every value it carried has already expired. Nothing in the
    observation times marks the row as report-anchored; the count does."""
    client, csrf = registered
    vehicle_id, _agent_id, credential = _source(client, csrf)
    base = datetime.now(UTC) - timedelta(minutes=20)
    # vehicle.in_use is not retained when stale, so once it expires it leaves
    # no reading behind at all.
    _upload(client, credential, [_sample(base, 0, {"vehicle.in_use": True})])

    table = client.get(
        f"/api/v1/vehicles/{vehicle_id}/history/table",
        params={
            "start": (base - timedelta(seconds=1)).isoformat(),
            "end": (base + timedelta(minutes=15)).isoformat(),
            "step_seconds": 300,
        },
    )
    assert table.status_code == 200, table.text
    rows = table.json()["rows"]
    assert sum(row["reports"] for row in rows) == 1
    anchored = [row for row in rows if row["reports"] == 1]
    assert len(anchored) == 1


def test_ingestion_rolls_back_history_candidates_state_and_jobs_together(
    registered: tuple[TestClient, str],
    db_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, csrf = registered
    vehicle_id, _agent_id, credential = _source(client, csrf)
    at = datetime.now(UTC)

    def fail_enqueue(_db: Session, _samples: list[Telemetry]) -> None:
        raise RuntimeError("queue unavailable")

    monkeypatch.setattr("backend.app.telemetry.services._enqueue_hooks", fail_enqueue)
    with pytest.raises(RuntimeError, match="queue unavailable"):
        _upload(client, credential, [_sample(at, 0, {"battery.soc": 50})])

    with db_factory() as db:
        assert db.scalar(select(func.count(Telemetry.id))) == 0
        assert db.scalar(select(func.count(TelemetryObservation.id))) == 0
        assert db.scalar(select(func.count()).select_from(MetricCandidate)) == 0
        assert db.get(VehicleState, vehicle_id) is None
