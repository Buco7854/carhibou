from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select, update

from backend.app.auth.dependencies import CurrentUser, CurrentUserWrite, Db
from backend.app.dashboards.models import Dashboard
from backend.app.dashboards.schemas import DashboardResponse, DashboardWrite

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


@router.get(
    "",
    response_model=list[DashboardResponse],
    response_model_exclude_none=True,
    response_model_exclude_defaults=True,
)
def list_dashboards(db: Db, auth: CurrentUser) -> list[Dashboard]:
    return list(
        db.scalars(
            select(Dashboard)
            .where(Dashboard.owner_id == auth.user.id)
            .order_by(Dashboard.created_at)
        )
    )


@router.post(
    "",
    response_model=DashboardResponse,
    response_model_exclude_none=True,
    response_model_exclude_defaults=True,
    status_code=status.HTTP_201_CREATED,
)
def create_dashboard(data: DashboardWrite, db: Db, auth: CurrentUserWrite) -> Dashboard:
    if data.is_default:
        db.execute(
            update(Dashboard).where(Dashboard.owner_id == auth.user.id).values(is_default=False)
        )
    values = data.model_dump()
    values["layout"] = data.layout.model_dump(exclude_none=True, exclude_defaults=True)
    dashboard = Dashboard(owner_id=auth.user.id, **values)
    db.add(dashboard)
    db.commit()
    return dashboard


@router.put(
    "/{dashboard_id}",
    response_model=DashboardResponse,
    response_model_exclude_none=True,
    response_model_exclude_defaults=True,
)
def update_dashboard(
    dashboard_id: str, data: DashboardWrite, db: Db, auth: CurrentUserWrite
) -> Dashboard:
    dashboard = db.scalar(
        select(Dashboard).where(Dashboard.id == dashboard_id, Dashboard.owner_id == auth.user.id)
    )
    if not dashboard:
        raise HTTPException(status_code=404, detail="dashboard not found")
    if data.is_default:
        db.execute(
            update(Dashboard)
            .where(Dashboard.owner_id == auth.user.id, Dashboard.id != dashboard.id)
            .values(is_default=False)
        )
    values = data.model_dump()
    values["layout"] = data.layout.model_dump(exclude_none=True, exclude_defaults=True)
    for key, value in values.items():
        setattr(dashboard, key, value)
    db.commit()
    return dashboard


@router.delete("/{dashboard_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dashboard(dashboard_id: str, db: Db, auth: CurrentUserWrite) -> None:
    dashboard = db.scalar(
        select(Dashboard).where(Dashboard.id == dashboard_id, Dashboard.owner_id == auth.user.id)
    )
    if not dashboard:
        raise HTTPException(status_code=404, detail="dashboard not found")
    db.delete(dashboard)
    db.commit()
