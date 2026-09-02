from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.agents.models import Agent
from backend.app.common.time import as_utc, utcnow
from backend.app.connectors.models import Connector
from backend.app.telemetry.contacts import latest_contact_periods
from backend.app.telemetry.models import MetricCandidate, PositionCandidate
from backend.app.telemetry.registry import (
    CHARGING_POWER_FLOOR_KW,
    FRESHNESS_INTERVAL_MULTIPLIER,
    definition_for,
    observation_is_fresh,
)
from backend.app.telemetry.schemas import Channel, Method, SourceKind
from backend.app.telemetry.values import MetricValue, finite_number


@dataclass(frozen=True)
class Candidate:
    key: str
    value: MetricValue
    observed_at: datetime
    source_id: str
    source_kind: SourceKind
    channel: Channel
    method: Method
    reporting_interval: int | None = None
    event_driven: bool = False
    source_last_contact_at: datetime | None = None
    source_liveness_window_seconds: int | None = None


@dataclass(frozen=True)
class PositionCandidateValue:
    value: dict[str, Any]
    observed_at: datetime
    source_id: str
    source_kind: SourceKind
    channel: Channel
    method: Method
    reporting_interval: int | None = None
    event_driven: bool = False
    source_last_contact_at: datetime | None = None
    source_liveness_window_seconds: int | None = None


def candidate_is_fresh(candidate: Candidate, now: datetime) -> bool:
    return observation_is_fresh(
        candidate.key,
        candidate.observed_at,
        now,
        reporting_interval=candidate.reporting_interval,
        event_driven=candidate.event_driven,
        source_last_contact_at=candidate.source_last_contact_at,
        source_liveness_window_seconds=candidate.source_liveness_window_seconds,
    )


def _reading(candidate: Candidate, now: datetime, *, fresh: bool | None = None) -> dict[str, Any]:
    return {
        "value": candidate.value,
        "observed_at": as_utc(candidate.observed_at).isoformat(),
        "source_id": candidate.source_id,
        "source_kind": candidate.source_kind,
        "channel": candidate.channel,
        "method": candidate.method,
        "fresh": candidate_is_fresh(candidate, now) if fresh is None else fresh,
    }


def _priority(candidate: Candidate) -> tuple[int, int, datetime]:
    direct = 1 if candidate.method == "direct" else 0
    channel = {"can": 5, "obd": 4, "gnss": 3, "mqtt": 2, "derived": 1}.get(candidate.channel, 0)
    return direct, channel, as_utc(candidate.observed_at)


def _choose(key: str, candidates: list[Candidate], now: datetime) -> Candidate | None:
    usable = [candidate for candidate in candidates if candidate.value is not None]
    fresh = [candidate for candidate in usable if candidate_is_fresh(candidate, now)]
    if fresh:
        if key == "vehicle.speed":
            road = [candidate for candidate in fresh if candidate.channel in {"can", "obd"}]
            if road:
                fresh = road
        return max(fresh, key=_priority)
    definition = definition_for(key)
    if usable and (definition is None or definition.retain_stale):
        return max(usable, key=_priority)
    return None


def _derived(origin: Candidate, key: str, value: MetricValue) -> Candidate:
    return Candidate(
        key=key,
        value=value,
        observed_at=origin.observed_at,
        source_id=origin.source_id,
        source_kind=origin.source_kind,
        channel="derived",
        method="derived",
        reporting_interval=origin.reporting_interval,
        event_driven=origin.event_driven,
        source_last_contact_at=origin.source_last_contact_at,
        source_liveness_window_seconds=origin.source_liveness_window_seconds,
    )


def resolve_readings(
    candidates: list[Candidate], now: datetime | None = None
) -> dict[str, dict[str, Any]]:
    resolved_at = as_utc(now or utcnow())
    by_key: dict[str, list[Candidate]] = {}
    for candidate in candidates:
        by_key.setdefault(candidate.key, []).append(candidate)

    readings: dict[str, dict[str, Any]] = {}
    for key, choices in by_key.items():
        if key in {"charging.active", "charging.power"}:
            continue
        selected = _choose(key, choices, resolved_at)
        if selected is not None:
            readings[key] = _reading(selected, resolved_at)

    explicit = _choose("charging.active", by_key.get("charging.active", []), resolved_at)
    if explicit is not None and candidate_is_fresh(explicit, resolved_at):
        readings["charging.active"] = _reading(explicit, resolved_at)
        active: bool | None = explicit.value is True
    else:
        active = None
        evidence = _choose("charging.power", by_key.get("charging.power", []), resolved_at)
        battery = _choose("battery.power", by_key.get("battery.power", []), resolved_at)
        origin = evidence or battery
        power = finite_number(evidence.value) if evidence else None
        battery_power = finite_number(battery.value) if battery else None
        if origin and candidate_is_fresh(origin, resolved_at):
            active = bool(
                (power is not None and power >= CHARGING_POWER_FLOOR_KW)
                or (battery_power is not None and battery_power <= -CHARGING_POWER_FLOOR_KW)
            )
            readings["charging.active"] = _reading(
                _derived(origin, "charging.active", active), resolved_at, fresh=True
            )

    direct_power = _choose("charging.power", by_key.get("charging.power", []), resolved_at)
    if direct_power is not None:
        readings["charging.power"] = _reading(direct_power, resolved_at)
    elif active:
        battery = _choose("battery.power", by_key.get("battery.power", []), resolved_at)
        battery_power = finite_number(battery.value) if battery else None
        if battery and battery_power is not None and battery_power < 0:
            readings["charging.power"] = _reading(
                _derived(battery, "charging.power", abs(battery_power)),
                resolved_at,
                fresh=True,
            )
    return readings


def _position_is_fresh(candidate: PositionCandidateValue, now: datetime) -> bool:
    return observation_is_fresh(
        "vehicle.speed",
        candidate.observed_at,
        now,
        reporting_interval=candidate.reporting_interval,
        event_driven=candidate.event_driven,
        source_last_contact_at=candidate.source_last_contact_at,
        source_liveness_window_seconds=candidate.source_liveness_window_seconds,
    )


def resolve_position(
    candidates: list[PositionCandidateValue], now: datetime | None = None
) -> dict[str, Any] | None:
    if not candidates:
        return None
    resolved_at = as_utc(now or utcnow())
    fresh = [candidate for candidate in candidates if _position_is_fresh(candidate, resolved_at)]
    selected = max(
        fresh or candidates,
        key=lambda value: (value.method == "direct", as_utc(value.observed_at)),
    )
    return {
        **selected.value,
        "observed_at": as_utc(selected.observed_at).isoformat(),
        "source_id": selected.source_id,
        "source_kind": selected.source_kind,
        "channel": selected.channel,
        "method": selected.method,
        "fresh": _position_is_fresh(selected, resolved_at),
    }


def load_candidates(
    db: Session, vehicle_id: str
) -> tuple[list[Candidate], list[PositionCandidateValue]]:
    metric_rows = list(
        db.scalars(select(MetricCandidate).where(MetricCandidate.vehicle_id == vehicle_id))
    )
    position_rows = list(
        db.scalars(select(PositionCandidate).where(PositionCandidate.vehicle_id == vehicle_id))
    )
    source_ids = {row.source_id for row in metric_rows} | {row.source_id for row in position_rows}
    connector_ids = (
        set(db.scalars(select(Connector.id).where(Connector.id.in_(source_ids))))
        if source_ids
        else set()
    )
    contacts = latest_contact_periods(db, source_ids)

    def kind(source_id: str) -> SourceKind:
        return "connector" if source_id in connector_ids else "agent"

    def contact(source_id: str) -> tuple[datetime | None, int | None]:
        row = contacts.get(source_id)
        return (row.last_contact_at, row.liveness_window_seconds) if row else (None, None)

    metrics: list[Candidate] = []
    for metric_row in metric_rows:
        last_contact_at, liveness = contact(metric_row.source_id)
        metrics.append(
            Candidate(
                key=metric_row.metric_key,
                value=metric_row.value,
                observed_at=metric_row.observed_at,
                source_id=metric_row.source_id,
                source_kind=kind(metric_row.source_id),
                channel=metric_row.channel,  # type: ignore[arg-type]
                method=metric_row.method,  # type: ignore[arg-type]
                reporting_interval=metric_row.reporting_interval,
                event_driven=metric_row.event_driven,
                source_last_contact_at=last_contact_at,
                source_liveness_window_seconds=liveness,
            )
        )
    positions: list[PositionCandidateValue] = []
    for position_row in position_rows:
        last_contact_at, liveness = contact(position_row.source_id)
        positions.append(
            PositionCandidateValue(
                value=dict(position_row.value),
                observed_at=position_row.observed_at,
                source_id=position_row.source_id,
                source_kind=kind(position_row.source_id),
                channel=position_row.channel,  # type: ignore[arg-type]
                method=position_row.method,  # type: ignore[arg-type]
                reporting_interval=position_row.reporting_interval,
                event_driven=position_row.event_driven,
                source_last_contact_at=last_contact_at,
                source_liveness_window_seconds=liveness,
            )
        )
    return metrics, positions


def resolve_vehicle(
    db: Session, vehicle_id: str, now: datetime | None = None
) -> tuple[dict[str, dict[str, Any]], dict[str, Any] | None]:
    metrics, positions = load_candidates(db, vehicle_id)
    return resolve_readings(metrics, now), resolve_position(positions, now)


def vehicle_source_online(
    db: Session,
    vehicle_id: str,
    default_threshold_seconds: int,
    now: datetime | None = None,
) -> bool:
    resolved_at = as_utc(now or utcnow())
    # A retired source cannot come back, so its last contact must not keep a
    # vehicle looking online for as long as the window lasts.
    source_ids = set(
        db.scalars(
            select(Agent.id).where(Agent.vehicle_id == vehicle_id, Agent.retired_at.is_(None))
        )
    )
    contacts = latest_contact_periods(db, source_ids).values()
    return any(
        as_utc(contact.last_contact_at)
        >= resolved_at
        - timedelta(
            seconds=max(
                default_threshold_seconds,
                FRESHNESS_INTERVAL_MULTIPLIER * contact.liveness_window_seconds,
            )
        )
        for contact in contacts
    )
