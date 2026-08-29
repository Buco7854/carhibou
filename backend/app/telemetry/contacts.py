from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.common.time import as_utc
from backend.app.telemetry.models import SourceContactPeriod


def latest_contact_periods(
    db: Session,
    source_ids: Iterable[str],
    *,
    at: datetime | None = None,
) -> dict[str, SourceContactPeriod]:
    identifiers = set(source_ids)
    if not identifiers:
        return {}
    ranked = select(
        SourceContactPeriod.id.label("id"),
        func.row_number()
        .over(
            partition_by=SourceContactPeriod.source_id,
            order_by=(
                SourceContactPeriod.started_at.desc(),
                SourceContactPeriod.id.desc(),
            ),
        )
        .label("rank"),
    ).where(SourceContactPeriod.source_id.in_(identifiers))
    if at is not None:
        ranked = ranked.where(SourceContactPeriod.started_at <= as_utc(at))
    ranked_rows = ranked.subquery()
    rows = db.scalars(
        select(SourceContactPeriod)
        .join(ranked_rows, ranked_rows.c.id == SourceContactPeriod.id)
        .where(ranked_rows.c.rank == 1)
    )
    return {row.source_id: row for row in rows}


def latest_contact_period(
    db: Session,
    source_id: str,
    *,
    at: datetime | None = None,
) -> SourceContactPeriod | None:
    return latest_contact_periods(db, {source_id}, at=at).get(source_id)
