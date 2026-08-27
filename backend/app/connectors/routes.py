from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from backend.app.access.constants import OPERATE, level_allows
from backend.app.access.dependencies import OperateVehicle
from backend.app.access.services import access_level, visible_vehicle_ids
from backend.app.auth.dependencies import CurrentUser, CurrentUserWrite, Db
from backend.app.connectors.catalog import CONNECTOR_KINDS
from backend.app.connectors.models import Connector
from backend.app.connectors.schemas import (
    ConnectorCreate,
    ConnectorKindResponse,
    ConnectorResponse,
    ConnectorUpdate,
)
from backend.app.connectors.services import (
    connector_response,
    create_connector,
    delete_connector,
    update_connector,
)
from backend.app.users.models import User

router = APIRouter(tags=["connectors"])


def _authorized_connector(db: Db, user: User, connector_id: str) -> Connector:
    connector = db.get(Connector, connector_id)
    level = access_level(db, user, connector.vehicle_id) if connector else None
    if not connector or level is None:
        raise HTTPException(status_code=404, detail="connector not found")
    if not level_allows(level, OPERATE):
        raise HTTPException(status_code=403, detail="permission denied")
    return connector


@router.get("/connector-kinds", response_model=list[ConnectorKindResponse])
def connector_kinds(auth: CurrentUser) -> tuple[ConnectorKindResponse, ...]:
    del auth
    return CONNECTOR_KINDS


@router.get("/connectors", response_model=list[ConnectorResponse])
def connectors(db: Db, auth: CurrentUser) -> list[ConnectorResponse]:
    visible = visible_vehicle_ids(db, auth.user)
    if not visible:
        return []
    rows = db.scalars(
        select(Connector).where(Connector.vehicle_id.in_(visible)).order_by(Connector.created_at)
    )
    return [connector_response(connector) for connector in rows]


@router.post(
    "/vehicles/{vehicle_id}/connectors",
    response_model=ConnectorResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_connector(data: ConnectorCreate, db: Db, authorized: OperateVehicle) -> ConnectorResponse:
    try:
        connector = create_connector(db, authorized.vehicle, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(connector)
    return connector_response(connector)


@router.put("/connectors/{connector_id}", response_model=ConnectorResponse)
def edit_connector(
    connector_id: str, data: ConnectorUpdate, db: Db, auth: CurrentUserWrite
) -> ConnectorResponse:
    connector = _authorized_connector(db, auth.user, connector_id)
    update_connector(db, connector, data)
    db.commit()
    db.refresh(connector)
    return connector_response(connector)


@router.delete("/connectors/{connector_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_connector(connector_id: str, db: Db, auth: CurrentUserWrite) -> None:
    connector = _authorized_connector(db, auth.user, connector_id)
    delete_connector(db, connector)
    db.commit()
