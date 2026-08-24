from datetime import datetime, timedelta
from math import ceil

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from backend.app.auth.dependencies import CurrentUser, Db
from backend.app.common.time import utcnow
from backend.app.history.schemas import HistoryPoint, HistoryResponse
from backend.app.telemetry.models import Telemetry
from backend.app.vehicles.services import owned_vehicle

router = APIRouter(prefix="/vehicles/{vehicle_id}/history", tags=["history"])


@router.get("", response_model=HistoryResponse)
def history(
    vehicle_id: str,
    db: Db,
    auth: CurrentUser,
    start: datetime | None = None,
    end: datetime | None = None,
    max_points: int = Query(default=1000, ge=10, le=5000),
) -> HistoryResponse:
    if not owned_vehicle(db, auth.user.id, vehicle_id):
        raise HTTPException(status_code=404, detail="vehicle not found")
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
    if db.get_bind().dialect.name == "postgresql":
        metric_names = db.scalars(
            select(func.jsonb_object_keys(Telemetry.metrics)).where(*where).distinct()
        )
        metrics = sorted(str(name) for name in metric_names)
    else:
        metric_values = db.scalars(select(Telemetry.metrics).where(*where))
        metrics = sorted({name for value in metric_values for name in value})
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
