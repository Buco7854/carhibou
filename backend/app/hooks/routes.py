from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from backend.app.auth.dependencies import (
    AuthenticatedUser,
    CurrentUser,
    Db,
    require_permission,
)
from backend.app.hooks.models import Hook, HookExecution, HookRevision
from backend.app.hooks.schemas import (
    HookExecutionResponse,
    HookResponse,
    HookRevisionResponse,
    HookTestRequest,
    HookWrite,
)
from backend.app.hooks.services import (
    HookValidationError,
    create_hook,
    queue_manual_execution,
    update_hook,
)
from backend.app.telemetry.models import Telemetry
from backend.app.vehicles.models import Vehicle

ManageHooks = Annotated[AuthenticatedUser, Depends(require_permission("hooks.manage_code"))]
router = APIRouter(prefix="/hooks", tags=["hooks"])


def _owned_hook(db: Db, owner_id: str, hook_id: str) -> Hook:
    hook = db.scalar(select(Hook).where(Hook.id == hook_id, Hook.owner_id == owner_id))
    if not hook:
        raise HTTPException(status_code=404, detail="hook not found")
    return hook


@router.get("", response_model=list[HookResponse])
def hooks(db: Db, auth: CurrentUser) -> list[Hook]:
    return list(db.scalars(select(Hook).where(Hook.owner_id == auth.user.id).order_by(Hook.name)))


@router.post("", response_model=HookResponse, status_code=status.HTTP_201_CREATED)
def add_hook(data: HookWrite, db: Db, auth: ManageHooks) -> Hook:
    try:
        hook = create_hook(db, auth.user, data)
    except HookValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return hook


@router.put("/{hook_id}", response_model=HookResponse)
def edit_hook(hook_id: str, data: HookWrite, db: Db, auth: ManageHooks) -> Hook:
    hook = _owned_hook(db, auth.user.id, hook_id)
    try:
        update_hook(db, hook, auth.user, data)
    except HookValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return hook


@router.delete("/{hook_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_hook(hook_id: str, db: Db, auth: ManageHooks) -> None:
    hook = _owned_hook(db, auth.user.id, hook_id)
    db.delete(hook)
    db.commit()


@router.get("/{hook_id}/revisions", response_model=list[HookRevisionResponse])
def revisions(hook_id: str, db: Db, auth: CurrentUser) -> list[HookRevision]:
    _owned_hook(db, auth.user.id, hook_id)
    return list(
        db.scalars(
            select(HookRevision)
            .where(HookRevision.hook_id == hook_id)
            .order_by(HookRevision.revision.desc())
        )
    )


@router.post("/{hook_id}/revisions/{revision}/restore", response_model=HookResponse)
def restore_revision(hook_id: str, revision: int, db: Db, auth: ManageHooks) -> Hook:
    hook = _owned_hook(db, auth.user.id, hook_id)
    saved = db.scalar(
        select(HookRevision).where(
            HookRevision.hook_id == hook_id, HookRevision.revision == revision
        )
    )
    if not saved:
        raise HTTPException(status_code=404, detail="hook revision not found")
    update_hook(
        db,
        hook,
        auth.user,
        HookWrite(
            name=hook.name,
            description=hook.description,
            enabled=hook.enabled,
            trigger_type="telemetry.received",
            vehicle_id=hook.vehicle_id,
            source=saved.source,
            timeout_seconds=hook.timeout_seconds,
        ),
    )
    db.commit()
    return hook


@router.post("/{hook_id}/test", response_model=HookExecutionResponse)
def test_hook(hook_id: str, data: HookTestRequest, db: Db, auth: ManageHooks) -> HookExecution:
    hook = _owned_hook(db, auth.user.id, hook_id)
    telemetry = db.scalar(
        select(Telemetry)
        .join(Vehicle)
        .where(Telemetry.id == data.telemetry_id, Vehicle.owner_id == auth.user.id)
    )
    if not telemetry:
        raise HTTPException(status_code=404, detail="telemetry sample not found")
    execution = queue_manual_execution(db, hook, telemetry, data.dry_run)
    db.commit()
    return execution


@router.get("/{hook_id}/executions", response_model=list[HookExecutionResponse])
def executions(
    hook_id: str,
    db: Db,
    auth: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[HookExecution]:
    _owned_hook(db, auth.user.id, hook_id)
    return list(
        db.scalars(
            select(HookExecution)
            .where(HookExecution.hook_id == hook_id)
            .order_by(HookExecution.created_at.desc())
            .limit(limit)
        )
    )


@router.post("/executions/{execution_id}/retry", response_model=HookExecutionResponse)
def retry_execution(execution_id: str, db: Db, auth: ManageHooks) -> HookExecution:
    old = db.scalar(
        select(HookExecution)
        .join(Hook)
        .where(HookExecution.id == execution_id, Hook.owner_id == auth.user.id)
    )
    if not old:
        raise HTTPException(status_code=404, detail="execution not found")
    if old.status not in {"failed", "timeout"}:
        raise HTTPException(status_code=409, detail="only failed executions can be retried")
    telemetry = db.get(Telemetry, old.telemetry_id) if old.telemetry_id else None
    hook = db.get(Hook, old.hook_id)
    if not telemetry or not hook:
        raise HTTPException(status_code=409, detail="execution source data is unavailable")
    execution = queue_manual_execution(db, hook, telemetry, old.dry_run)
    db.commit()
    return execution
