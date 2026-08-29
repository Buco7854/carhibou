from datetime import datetime, timedelta
from math import ceil
from typing import Annotated, Literal, NamedTuple

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from backend.app.access.dependencies import ViewVehicle
from backend.app.auth.dependencies import Db
from backend.app.common.time import utcnow
from backend.app.connectors.models import Connector
from backend.app.history.reconstruction import table_rows
from backend.app.history.schemas import (
    HistoryEntriesResponse,
    HistoryEntry,
    HistoryObservationSample,
    HistoryObservationsResponse,
    HistoryPoint,
    HistoryResponse,
    HistoryTableResponse,
    RecordedObservation,
    RecordedPosition,
)
from backend.app.telemetry.models import (
    Telemetry,
    TelemetryObservation,
    TelemetryPositionObservation,
)

router = APIRouter(prefix="/vehicles/{vehicle_id}/history", tags=["history"])
TABLE_STEPS = {1, 5, 10, 30, 60, 300, 900, 3600, 21600, 86400}


def _range(start: datetime | None, end: datetime | None) -> tuple[datetime, datetime]:
    resolved_end = end or utcnow()
    resolved_start = start or resolved_end - timedelta(hours=24)
    if resolved_start >= resolved_end:
        raise HTTPException(status_code=400, detail="start must be earlier than end")
    return resolved_start, resolved_end


def _children(
    db: Db, rows: list[Telemetry]
) -> tuple[
    dict[str, list[TelemetryObservation]],
    dict[str, TelemetryPositionObservation],
    set[str],
]:
    ids = [row.id for row in rows]
    if not ids:
        return {}, {}, set()
    observations: dict[str, list[TelemetryObservation]] = {}
    source_ids = {row.agent_id for row in rows}
    for item in db.scalars(
        select(TelemetryObservation)
        .where(TelemetryObservation.telemetry_id.in_(ids))
        .order_by(TelemetryObservation.observed_at, TelemetryObservation.id)
    ):
        observations.setdefault(item.telemetry_id, []).append(item)
    positions = {
        item.telemetry_id: item
        for item in db.scalars(
            select(TelemetryPositionObservation).where(
                TelemetryPositionObservation.telemetry_id.in_(ids)
            )
        )
    }
    connector_ids = set(db.scalars(select(Connector.id).where(Connector.id.in_(source_ids))))
    return observations, positions, connector_ids


def _metric_values(items: list[TelemetryObservation]) -> dict[str, object]:
    return {item.metric_key: item.payload.get("value") for item in items}


def _position_values(
    item: TelemetryPositionObservation | None,
) -> tuple[float | None, float | None, float | None, float | None, float | None, float | None]:
    value = item.value if item else {}
    return (
        value.get("latitude"),
        value.get("longitude"),
        value.get("altitude"),
        value.get("speed"),
        value.get("heading"),
        value.get("accuracy"),
    )


@router.get("", response_model=HistoryResponse)
def history(
    vehicle_id: str,
    db: Db,
    authorized: ViewVehicle,
    start: datetime | None = None,
    end: datetime | None = None,
    max_points: int = Query(default=1000, ge=10, le=5000),
) -> HistoryResponse:
    del authorized
    resolved_start, resolved_end = _range(start, end)
    where = (
        Telemetry.vehicle_id == vehicle_id,
        Telemetry.recorded_at >= resolved_start,
        Telemetry.recorded_at <= resolved_end,
    )
    count = db.scalar(select(func.count(Telemetry.id)).where(*where)) or 0
    rows = list(
        db.scalars(select(Telemetry).where(*where).order_by(Telemetry.recorded_at, Telemetry.id))
    )
    if len(rows) > max_points:
        stride = max(1, ceil(len(rows) / max_points))
        rows = rows[::stride]
        last = db.scalar(
            select(Telemetry)
            .where(*where)
            .order_by(Telemetry.recorded_at.desc(), Telemetry.id.desc())
            .limit(1)
        )
        if last and rows[-1].id != last.id:
            rows.append(last)
    observations, positions, _connector_ids = _children(db, rows)
    metric_keys = list(
        db.scalars(
            select(TelemetryObservation.metric_key)
            .where(
                TelemetryObservation.vehicle_id == vehicle_id,
                TelemetryObservation.observed_at >= resolved_start,
                TelemetryObservation.observed_at <= resolved_end,
            )
            .distinct()
            .order_by(TelemetryObservation.metric_key)
        )
    )
    points = []
    for row in rows:
        latitude, longitude, _altitude, speed, heading, _accuracy = _position_values(
            positions.get(row.id)
        )
        points.append(
            HistoryPoint(
                id=row.id,
                recorded_at=row.recorded_at,
                latitude=latitude,
                longitude=longitude,
                speed=speed,
                heading=heading,
                metrics=_metric_values(observations.get(row.id, [])),
            )
        )
    return HistoryResponse(
        vehicle_id=vehicle_id,
        start=resolved_start,
        end=resolved_end,
        available_metrics=metric_keys,
        original_count=count,
        points=points,
    )


class _EntryFilter(NamedTuple):
    column: str
    minimum: float | None
    maximum: float | None
    present: bool


def _parse_filter(raw: str) -> _EntryFilter:
    parts = raw.split("|")
    if len(parts) > 4:
        raise HTTPException(status_code=400, detail=f"malformed filter: {raw}")
    parts += [""] * (4 - len(parts))
    column, minimum, maximum, present = (part.strip() for part in parts)
    if not column:
        raise HTTPException(status_code=400, detail="filter is missing its column")

    def bound(text: str) -> float | None:
        try:
            return float(text) if text else None
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"filter bound is not a number: {text}"
            ) from None

    return _EntryFilter(
        column,
        bound(minimum),
        bound(maximum),
        present.lower() in {"1", "true", "yes"},
    )


def _column(entry: HistoryEntry, key: str) -> object:
    fixed = {
        "recorded_at": entry.recorded_at,
        "sequence": entry.sequence,
        "latitude": entry.latitude,
        "longitude": entry.longitude,
        "altitude": entry.altitude,
        "speed": entry.speed,
        "heading": entry.heading,
        "accuracy": entry.accuracy,
    }
    if key in fixed:
        return fixed[key]
    prefix, _, name = key.partition(":")
    if prefix == "metric" and name:
        return entry.metrics.get(name)
    if prefix == "agent" and name:
        return entry.agent.get(name)
    raise HTTPException(status_code=400, detail=f"unknown column: {key}")


@router.get("/entries", response_model=HistoryEntriesResponse)
def history_entries(
    vehicle_id: str,
    db: Db,
    authorized: ViewVehicle,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    sort: str = Query(default="recorded_at", max_length=140),
    direction: Literal["asc", "desc"] = "desc",
    filters: Annotated[list[str] | None, Query(alias="filter", max_length=12)] = None,
) -> HistoryEntriesResponse:
    del authorized
    resolved_start, resolved_end = _range(start, end)
    rows = list(
        db.scalars(
            select(Telemetry)
            .where(
                Telemetry.vehicle_id == vehicle_id,
                Telemetry.recorded_at >= resolved_start,
                Telemetry.recorded_at <= resolved_end,
            )
            .order_by(Telemetry.recorded_at, Telemetry.id)
        )
    )
    observations, positions, _connector_ids = _children(db, rows)
    entries = []
    for row in rows:
        latitude, longitude, altitude, speed, heading, accuracy = _position_values(
            positions.get(row.id)
        )
        entries.append(
            HistoryEntry(
                id=row.id,
                recorded_at=row.recorded_at,
                sequence=row.sequence,
                latitude=latitude,
                longitude=longitude,
                altitude=altitude,
                speed=speed,
                heading=heading,
                accuracy=accuracy,
                metrics=_metric_values(observations.get(row.id, [])),
                agent=row.agent_data,
            )
        )
    for raw in filters or []:
        parsed = _parse_filter(raw)
        filtered = []
        for entry in entries:
            value = _column(entry, parsed.column)
            if parsed.present and value is None:
                continue
            numeric = (
                float(value)
                if isinstance(value, (int, float)) and not isinstance(value, bool)
                else None
            )
            if parsed.minimum is not None and (numeric is None or numeric < parsed.minimum):
                continue
            if parsed.maximum is not None and (numeric is None or numeric > parsed.maximum):
                continue
            filtered.append(entry)
        entries = filtered
    _column(entries[0], sort) if entries else _column(
        HistoryEntry(
            id="",
            recorded_at=resolved_start,
            sequence=0,
            latitude=None,
            longitude=None,
            altitude=None,
            speed=None,
            heading=None,
            accuracy=None,
            metrics={},
            agent={},
        ),
        sort,
    )
    present_entries = [entry for entry in entries if _column(entry, sort) is not None]
    missing_entries = [entry for entry in entries if _column(entry, sort) is None]

    def sort_value(entry: HistoryEntry) -> tuple[int, float | str]:
        value = _column(entry, sort)
        if isinstance(value, datetime):
            return 0, value.timestamp()
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return 0, float(value)
        return 1, str(value)

    present_entries.sort(key=sort_value, reverse=direction == "desc")
    entries = present_entries + missing_entries
    metric_keys = sorted({key for entry in entries for key in entry.metrics})
    agent_keys = sorted({key for entry in entries for key in entry.agent})
    total = len(entries)
    return HistoryEntriesResponse(
        vehicle_id=vehicle_id,
        start=resolved_start,
        end=resolved_end,
        total=total,
        limit=limit,
        offset=offset,
        metric_keys=metric_keys,
        agent_keys=agent_keys,
        entries=entries[offset : offset + limit],
    )


@router.get("/observations", response_model=HistoryObservationsResponse)
def history_observations(
    vehicle_id: str,
    db: Db,
    authorized: ViewVehicle,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> HistoryObservationsResponse:
    del authorized
    resolved_start, resolved_end = _range(start, end)
    where = (
        Telemetry.vehicle_id == vehicle_id,
        Telemetry.recorded_at >= resolved_start,
        Telemetry.recorded_at <= resolved_end,
    )
    total = db.scalar(select(func.count(Telemetry.id)).where(*where)) or 0
    rows = list(
        db.scalars(
            select(Telemetry)
            .where(*where)
            .order_by(Telemetry.recorded_at.desc(), Telemetry.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    observations, positions, connector_ids = _children(db, rows)
    samples = []
    for row in rows:
        source_kind = "connector" if row.agent_id in connector_ids else "agent"
        position = positions.get(row.id)
        samples.append(
            HistoryObservationSample(
                id=row.id,
                sequence=row.sequence,
                recorded_at=row.recorded_at,
                received_at=row.received_at,
                source_id=row.agent_id,
                source_kind=source_kind,
                reporting_interval=row.reporting_interval,
                event_driven=row.event_driven,
                position=RecordedPosition(
                    value=position.value,
                    observed_at=position.observed_at,
                    source_id=position.source_id,
                    source_kind=source_kind,
                    channel=position.channel,
                    method=position.method,
                )
                if position
                else None,
                observations=[
                    RecordedObservation(
                        key=item.metric_key,
                        value=item.payload.get("value"),
                        observed_at=item.observed_at,
                        source_id=item.source_id,
                        source_kind=source_kind,
                        channel=item.channel,
                        method=item.method,
                    )
                    for item in observations.get(row.id, [])
                ],
                agent=row.agent_data,
            )
        )
    return HistoryObservationsResponse(
        vehicle_id=vehicle_id,
        start=resolved_start,
        end=resolved_end,
        total=total,
        limit=limit,
        offset=offset,
        samples=samples,
    )


@router.get("/table", response_model=HistoryTableResponse)
def history_table(
    vehicle_id: str,
    db: Db,
    authorized: ViewVehicle,
    start: datetime | None = None,
    end: datetime | None = None,
    step_seconds: int = Query(default=60),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> HistoryTableResponse:
    del authorized
    if step_seconds not in TABLE_STEPS:
        raise HTTPException(status_code=400, detail="unsupported history table resolution")
    resolved_start, resolved_end = _range(start, end)
    rows = table_rows(db, vehicle_id, resolved_start, resolved_end, step_seconds)
    return HistoryTableResponse(
        vehicle_id=vehicle_id,
        start=resolved_start,
        end=resolved_end,
        step_seconds=step_seconds,
        total=len(rows),
        limit=limit,
        offset=offset,
        rows=rows[offset : offset + limit],
    )
