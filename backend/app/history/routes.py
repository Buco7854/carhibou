from collections.abc import Sequence
from datetime import datetime, timedelta
from math import ceil
from typing import Annotated, Any, Literal, NamedTuple

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import Float, case, func, select
from sqlalchemy.orm import InstrumentedAttribute

from backend.app.access.dependencies import ViewVehicle
from backend.app.auth.dependencies import Db
from backend.app.common.time import utcnow
from backend.app.common.types import JSONValue
from backend.app.history.schemas import (
    HistoryEntriesResponse,
    HistoryEntry,
    HistoryPoint,
    HistoryResponse,
)
from backend.app.telemetry.models import Telemetry

router = APIRouter(prefix="/vehicles/{vehicle_id}/history", tags=["history"])

FIXED_COLUMNS: dict[str, Any] = {
    "recorded_at": Telemetry.recorded_at,
    "sequence": Telemetry.sequence,
    "latitude": Telemetry.latitude,
    "longitude": Telemetry.longitude,
    "altitude": Telemetry.altitude,
    "speed": Telemetry.gps_speed,
    "heading": Telemetry.heading,
    "accuracy": Telemetry.accuracy,
}


def _json_column(prefix: str) -> InstrumentedAttribute[JSONValue] | None:
    if prefix == "metric":
        return Telemetry.metrics
    if prefix == "agent":
        return Telemetry.agent_data
    return None


def _numeric_json(column: InstrumentedAttribute[JSONValue], key: str, dialect: str) -> Any:
    """Numeric view of one JSON key that never raises on non-numeric values.

    A straight cast is unsafe: PostgreSQL errors when a metric happens to hold text,
    so each dialect guards the cast with its own type probe.
    """
    if dialect == "postgresql":
        return case(
            (func.jsonb_typeof(column[key]) == "number", column[key].as_float()),
            else_=None,
        )
    path = "$." + '"' + key.replace('"', '\\"') + '"'
    return case(
        (
            func.json_type(column, path).in_(("integer", "real")),
            func.cast(func.json_extract(column, path), Float),
        ),
        else_=None,
    )


def _sortable(key: str, dialect: str) -> Any | None:
    if key in FIXED_COLUMNS:
        return FIXED_COLUMNS[key]
    prefix, _, name = key.partition(":")
    column = _json_column(prefix)
    if column is None or not name:
        return None
    return _numeric_json(column, name, dialect)


def _distinct_keys(
    db: Db, column: InstrumentedAttribute[JSONValue], where: Sequence[Any], dialect: str
) -> list[str]:
    if dialect == "postgresql":
        return sorted(
            str(name)
            for name in db.scalars(select(func.jsonb_object_keys(column)).where(*where).distinct())
        )
    values = db.scalars(select(column).where(*where))
    return sorted({name for value in values if value for name in value})


def _json_keys(db: Db, where: Sequence[Any], dialect: str) -> tuple[list[str], list[str]]:
    return (
        _distinct_keys(db, Telemetry.metrics, where, dialect),
        _distinct_keys(db, Telemetry.agent_data, where, dialect),
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
    resolved_end = end or utcnow()
    resolved_start = start or resolved_end - timedelta(hours=24)
    if resolved_start >= resolved_end:
        raise HTTPException(status_code=400, detail="start must be earlier than end")
    where = (
        Telemetry.vehicle_id == vehicle_id,
        Telemetry.recorded_at >= resolved_start,
        Telemetry.recorded_at <= resolved_end,
    )
    count = db.scalar(select(func.count(Telemetry.id)).where(*where)) or 0
    stride = max(1, ceil(count / max_points))
    numbered = (
        select(
            Telemetry.id.label("telemetry_id"),
            (func.row_number().over(order_by=(Telemetry.recorded_at, Telemetry.id)) - 1).label(
                "ordinal"
            ),
        )
        .where(*where)
        .subquery()
    )
    sampled_ids = select(numbered.c.telemetry_id).where(numbered.c.ordinal % stride == 0)
    selected = list(
        db.scalars(
            select(Telemetry)
            .where(Telemetry.id.in_(sampled_ids))
            .order_by(Telemetry.recorded_at, Telemetry.id)
        )
    )
    last = db.scalar(
        select(Telemetry)
        .where(*where)
        .order_by(Telemetry.recorded_at.desc(), Telemetry.id.desc())
        .limit(1)
    )
    if last and (not selected or selected[-1].id != last.id):
        selected.append(last)
    metrics = _distinct_keys(db, Telemetry.metrics, where, db.get_bind().dialect.name)
    return HistoryResponse(
        vehicle_id=vehicle_id,
        start=resolved_start,
        end=resolved_end,
        available_metrics=metrics,
        original_count=count,
        points=[
            HistoryPoint(
                id=row.id,
                recorded_at=row.recorded_at,
                latitude=row.latitude,
                longitude=row.longitude,
                speed=row.gps_speed,
                heading=row.heading,
                metrics=row.metrics,
            )
            for row in selected
        ],
    )


class _EntryFilter(NamedTuple):
    column: str
    minimum: float | None
    maximum: float | None
    present: bool


def _parse_filter(raw: str) -> _EntryFilter:
    """Decode one ``column|minimum|maximum|present`` filter.

    The separator is a pipe rather than a colon because a column key already
    contains one: a metric column is addressed as ``metric:battery.soc``. Any
    segment may be empty, so a lower bound alone is ``metric:battery.soc|20||``.
    """

    parts = raw.split("|")
    if len(parts) > 4:
        raise HTTPException(status_code=400, detail=f"malformed filter: {raw}")
    parts += [""] * (4 - len(parts))
    column, minimum, maximum, present = (part.strip() for part in parts)
    if not column:
        raise HTTPException(status_code=400, detail="filter is missing its column")

    def bound(text: str, name: str) -> float | None:
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"filter {name} is not a number: {text}"
            ) from None

    return _EntryFilter(
        column=column,
        minimum=bound(minimum, "minimum"),
        maximum=bound(maximum, "maximum"),
        present=present.lower() in {"1", "true", "yes"},
    )


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
    resolved_end = end or utcnow()
    resolved_start = start or resolved_end - timedelta(hours=24)
    if resolved_start >= resolved_end:
        raise HTTPException(status_code=400, detail="start must be earlier than end")
    dialect = db.get_bind().dialect.name
    order_column = _sortable(sort, dialect)
    if order_column is None:
        raise HTTPException(status_code=400, detail=f"unknown sort column: {sort}")

    where = [
        Telemetry.vehicle_id == vehicle_id,
        Telemetry.recorded_at >= resolved_start,
        Telemetry.recorded_at <= resolved_end,
    ]
    # Several filters narrow the same result set, so they combine with AND.
    for raw in filters or []:
        entry_filter = _parse_filter(raw)
        filtered = _sortable(entry_filter.column, dialect)
        if filtered is None:
            raise HTTPException(
                status_code=400, detail=f"unknown filter column: {entry_filter.column}"
            )
        if entry_filter.present:
            where.append(filtered.is_not(None))
        if entry_filter.minimum is not None:
            where.append(filtered >= entry_filter.minimum)
        if entry_filter.maximum is not None:
            where.append(filtered <= entry_filter.maximum)

    total = db.scalar(select(func.count(Telemetry.id)).where(*where)) or 0
    ordering = order_column.desc() if direction == "desc" else order_column.asc()
    # recorded_at breaks ties so paging stays stable when a sorted metric repeats.
    tiebreak = Telemetry.recorded_at.desc() if direction == "desc" else Telemetry.recorded_at.asc()
    rows = list(
        db.scalars(
            select(Telemetry)
            .where(*where)
            .order_by(ordering.nulls_last(), tiebreak, Telemetry.sequence)
            .limit(limit)
            .offset(offset)
        )
    )
    metric_keys, agent_keys = _json_keys(db, where, dialect)
    return HistoryEntriesResponse(
        vehicle_id=vehicle_id,
        start=resolved_start,
        end=resolved_end,
        total=total,
        limit=limit,
        offset=offset,
        metric_keys=metric_keys,
        agent_keys=agent_keys,
        entries=[
            HistoryEntry(
                id=row.id,
                recorded_at=row.recorded_at,
                sequence=row.sequence,
                latitude=row.latitude,
                longitude=row.longitude,
                altitude=row.altitude,
                speed=row.gps_speed,
                heading=row.heading,
                accuracy=row.accuracy,
                metrics=row.metrics,
                agent=row.agent_data,
            )
            for row in rows
        ],
    )
