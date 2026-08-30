from dataclasses import dataclass
from datetime import datetime, timedelta
from math import ceil, floor
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.common.time import as_utc
from backend.app.connectors.models import Connector
from backend.app.telemetry.contacts import latest_contact_periods
from backend.app.telemetry.models import (
    Telemetry,
    TelemetryObservation,
    TelemetryPositionObservation,
)
from backend.app.telemetry.registry import (
    FRESHNESS_INTERVAL_MULTIPLIER,
    SLOW_FRESHNESS,
    definition_for,
)
from backend.app.telemetry.resolution import (
    Candidate,
    PositionCandidateValue,
    resolve_position,
    resolve_readings,
)
from backend.app.telemetry.schemas import SourceKind


@dataclass
class CandidateState:
    metrics: dict[tuple[str, str, str], Candidate]
    positions: dict[tuple[str, str], PositionCandidateValue]
    agent: dict[str, Any]


@dataclass(frozen=True)
class TimedEvent:
    observed_at: datetime
    metric: Candidate | None = None
    position: PositionCandidateValue | None = None
    agent: dict[str, Any] | None = None


def _source_context(
    db: Session, source_ids: set[str], at: datetime
) -> tuple[set[str], dict[str, tuple[datetime, int]]]:
    if not source_ids:
        return set(), {}
    connectors = set(db.scalars(select(Connector.id).where(Connector.id.in_(source_ids))))
    contacts = {
        source_id: (
            min(as_utc(period.last_contact_at), as_utc(at)),
            period.liveness_window_seconds,
        )
        for source_id, period in latest_contact_periods(db, source_ids, at=at).items()
    }
    return connectors, contacts


def _kind(source_id: str, connectors: set[str]) -> SourceKind:
    return "connector" if source_id in connectors else "agent"


def _contact(
    source_id: str, contacts: dict[str, tuple[datetime, int]]
) -> tuple[datetime | None, int | None]:
    return contacts.get(source_id, (None, None))


def _metric_candidate(
    row: TelemetryObservation,
    sample: Telemetry,
    connectors: set[str],
    contacts: dict[str, tuple[datetime, int]],
) -> Candidate:
    last_contact, liveness = _contact(row.source_id, contacts)
    return Candidate(
        key=row.metric_key,
        value=row.value,
        observed_at=row.observed_at,
        source_id=row.source_id,
        source_kind=_kind(row.source_id, connectors),
        channel=row.channel,  # type: ignore[arg-type]
        method=row.method,  # type: ignore[arg-type]
        reporting_interval=sample.reporting_interval,
        event_driven=sample.event_driven,
        source_last_contact_at=last_contact,
        source_liveness_window_seconds=liveness,
    )


def _position_candidate(
    row: TelemetryPositionObservation,
    sample: Telemetry,
    connectors: set[str],
    contacts: dict[str, tuple[datetime, int]],
) -> PositionCandidateValue:
    last_contact, liveness = _contact(row.source_id, contacts)
    return PositionCandidateValue(
        value=dict(row.value),
        observed_at=row.observed_at,
        source_id=row.source_id,
        source_kind=_kind(row.source_id, connectors),
        channel=row.channel,  # type: ignore[arg-type]
        method=row.method,  # type: ignore[arg-type]
        reporting_interval=sample.reporting_interval,
        event_driven=sample.event_driven,
        source_last_contact_at=last_contact,
        source_liveness_window_seconds=liveness,
    )


def _latest_metric_rows(
    db: Session, vehicle_id: str, at: datetime
) -> list[tuple[TelemetryObservation, Telemetry]]:
    ranked = (
        select(
            TelemetryObservation.id.label("id"),
            func.row_number()
            .over(
                partition_by=(
                    TelemetryObservation.source_id,
                    TelemetryObservation.channel,
                    TelemetryObservation.metric_key,
                ),
                order_by=(
                    TelemetryObservation.observed_at.desc(),
                    TelemetryObservation.id.desc(),
                ),
            )
            .label("rank"),
        )
        .where(
            TelemetryObservation.vehicle_id == vehicle_id,
            TelemetryObservation.observed_at <= at,
        )
        .subquery()
    )
    return list(
        db.execute(
            select(TelemetryObservation, Telemetry)
            .join(ranked, ranked.c.id == TelemetryObservation.id)
            .join(Telemetry, Telemetry.id == TelemetryObservation.telemetry_id)
            .where(ranked.c.rank == 1)
        ).tuples()
    )


def _latest_position_rows(
    db: Session, vehicle_id: str, at: datetime
) -> list[tuple[TelemetryPositionObservation, Telemetry]]:
    ranked = (
        select(
            TelemetryPositionObservation.telemetry_id.label("telemetry_id"),
            func.row_number()
            .over(
                partition_by=(
                    TelemetryPositionObservation.source_id,
                    TelemetryPositionObservation.channel,
                ),
                order_by=TelemetryPositionObservation.observed_at.desc(),
            )
            .label("rank"),
        )
        .where(
            TelemetryPositionObservation.vehicle_id == vehicle_id,
            TelemetryPositionObservation.observed_at <= at,
        )
        .subquery()
    )
    return list(
        db.execute(
            select(TelemetryPositionObservation, Telemetry)
            .join(
                ranked,
                ranked.c.telemetry_id == TelemetryPositionObservation.telemetry_id,
            )
            .join(Telemetry, Telemetry.id == TelemetryPositionObservation.telemetry_id)
            .where(ranked.c.rank == 1)
        ).tuples()
    )


def candidate_state_at(db: Session, vehicle_id: str, at: datetime) -> CandidateState:
    metric_rows = _latest_metric_rows(db, vehicle_id, at)
    position_rows = _latest_position_rows(db, vehicle_id, at)
    source_ids = {row.source_id for row, _sample in metric_rows} | {
        row.source_id for row, _sample in position_rows
    }
    connectors, contacts = _source_context(db, source_ids, at)
    metrics = {
        (row.source_id, row.channel, row.metric_key): _metric_candidate(
            row, sample, connectors, contacts
        )
        for row, sample in metric_rows
    }
    positions = {
        (row.source_id, row.channel): _position_candidate(row, sample, connectors, contacts)
        for row, sample in position_rows
    }
    latest = db.scalar(
        select(Telemetry)
        .where(Telemetry.vehicle_id == vehicle_id, Telemetry.recorded_at <= at)
        .order_by(Telemetry.recorded_at.desc(), Telemetry.sequence.desc(), Telemetry.id.desc())
        .limit(1)
    )
    return CandidateState(metrics, positions, dict(latest.agent_data) if latest else {})


def resolved_state(state: CandidateState, at: datetime) -> dict[str, Any]:
    return {
        "readings": resolve_readings(list(state.metrics.values()), at),
        "position": resolve_position(list(state.positions.values()), at),
        "agent": dict(state.agent),
    }


def state_at_time(db: Session, vehicle_id: str, at: datetime) -> dict[str, Any]:
    return resolved_state(candidate_state_at(db, vehicle_id, at), at)


def _events(db: Session, vehicle_id: str, start: datetime, end: datetime) -> list[TimedEvent]:
    metric_pairs = list(
        db.execute(
            select(TelemetryObservation, Telemetry)
            .join(Telemetry, Telemetry.id == TelemetryObservation.telemetry_id)
            .where(
                TelemetryObservation.vehicle_id == vehicle_id,
                TelemetryObservation.observed_at > start,
                TelemetryObservation.observed_at <= end,
            )
            .order_by(TelemetryObservation.observed_at, TelemetryObservation.id)
        ).tuples()
    )
    position_pairs = list(
        db.execute(
            select(TelemetryPositionObservation, Telemetry)
            .join(Telemetry, Telemetry.id == TelemetryPositionObservation.telemetry_id)
            .where(
                TelemetryPositionObservation.vehicle_id == vehicle_id,
                TelemetryPositionObservation.observed_at > start,
                TelemetryPositionObservation.observed_at <= end,
            )
            .order_by(TelemetryPositionObservation.observed_at)
        ).tuples()
    )
    agent_rows = list(
        db.scalars(
            select(Telemetry)
            .where(
                Telemetry.vehicle_id == vehicle_id,
                Telemetry.recorded_at > start,
                Telemetry.recorded_at <= end,
            )
            .order_by(Telemetry.recorded_at, Telemetry.sequence, Telemetry.id)
        )
    )
    source_ids = {row.source_id for row, _sample in metric_pairs} | {
        row.source_id for row, _sample in position_pairs
    }
    connectors, contacts = _source_context(db, source_ids, end)
    events = [
        TimedEvent(row.observed_at, metric=_metric_candidate(row, sample, connectors, contacts))
        for row, sample in metric_pairs
    ]
    events.extend(
        TimedEvent(
            row.observed_at,
            position=_position_candidate(row, sample, connectors, contacts),
        )
        for row, sample in position_pairs
    )
    events.extend(TimedEvent(row.recorded_at, agent=dict(row.agent_data)) for row in agent_rows)
    return sorted(events, key=lambda event: as_utc(event.observed_at))


def _expiry(candidate: Candidate | PositionCandidateValue) -> datetime:
    key = candidate.key if isinstance(candidate, Candidate) else "vehicle.speed"
    definition = definition_for(key)
    freshness = definition.freshness if definition else SLOW_FRESHNESS
    if candidate.event_driven and candidate.source_last_contact_at is not None:
        return as_utc(candidate.source_last_contact_at) + max(
            freshness,
            timedelta(seconds=candidate.source_liveness_window_seconds or 0),
        )
    if candidate.reporting_interval is not None:
        freshness = max(
            freshness,
            timedelta(seconds=FRESHNESS_INTERVAL_MULTIPLIER * candidate.reporting_interval),
        )
    return as_utc(candidate.observed_at) + freshness


def table_rows(
    db: Session,
    vehicle_id: str,
    start: datetime,
    end: datetime,
    step_seconds: int,
) -> list[dict[str, Any]]:
    start = as_utc(start)
    end = as_utc(end)
    step = timedelta(seconds=step_seconds)
    bucket_count = max(1, ceil((end - start).total_seconds() / step_seconds))
    state = candidate_state_at(db, vehicle_id, start)
    events = _events(db, vehicle_id, start, end)

    relevant = {0, bucket_count - 1}
    for event in events:
        index = min(
            bucket_count - 1,
            max(0, floor((as_utc(event.observed_at) - start).total_seconds() / step_seconds)),
        )
        relevant.add(index)
        candidate = event.metric or event.position
        if candidate is not None:
            expiry = _expiry(candidate)
            if start < expiry < end:
                relevant.add(
                    min(
                        bucket_count - 1,
                        max(0, floor((expiry - start).total_seconds() / step_seconds)),
                    )
                )

    ordered = sorted(relevant)
    output: list[dict[str, Any]] = []
    event_index = 0
    for offset, index in enumerate(ordered):
        bucket_end = min(end, start + step * (index + 1))
        # Rows exist for two reasons: a report landed, or a candidate expired at
        # a moment nothing was reported. Counting the reports as they are
        # consumed tells the two apart exactly, where reading it back off the
        # observation times cannot: a report whose values had all already
        # expired carries no fresh observed_at to infer it from.
        reports = 0
        while event_index < len(events) and as_utc(events[event_index].observed_at) <= bucket_end:
            event = events[event_index]
            if event.metric:
                key = (event.metric.source_id, event.metric.channel, event.metric.key)
                state.metrics[key] = event.metric
            if event.position:
                position_key = (event.position.source_id, event.position.channel)
                state.positions[position_key] = event.position
                speed = event.position.value.get("speed")
                state.metrics[(event.position.source_id, "gnss", "vehicle.speed")] = Candidate(
                    key="vehicle.speed",
                    value=speed,
                    observed_at=event.position.observed_at,
                    source_id=event.position.source_id,
                    source_kind=event.position.source_kind,
                    channel="gnss",
                    method=event.position.method,
                    reporting_interval=event.position.reporting_interval,
                    event_driven=event.position.event_driven,
                    source_last_contact_at=event.position.source_last_contact_at,
                    source_liveness_window_seconds=event.position.source_liveness_window_seconds,
                )
            if event.agent is not None:
                state.agent.update(event.agent)
                reports += 1
            event_index += 1
        next_index = ordered[offset + 1] if offset + 1 < len(ordered) else bucket_count
        span_end = min(end, start + step * next_index)
        snapshot = resolved_state(state, bucket_end)
        # The count stays out of the signature: two spans that show the same
        # state are still the same row, however many reports built each of them.
        signature = snapshot
        if output and output[-1]["_signature"] == signature:
            output[-1]["bucket_end"] = span_end
            output[-1]["collapsed_buckets"] += next_index - index
            output[-1]["reports"] += reports
        else:
            output.append(
                {
                    "bucket_start": start + step * index,
                    "bucket_end": span_end,
                    "collapsed_buckets": next_index - index,
                    "reports": reports,
                    **snapshot,
                    "_signature": signature,
                }
            )
    for row in output:
        row.pop("_signature", None)
    return list(reversed(output))
