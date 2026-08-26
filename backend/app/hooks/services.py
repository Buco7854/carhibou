import textwrap

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.common.time import utcnow
from backend.app.hooks.models import Hook, HookExecution, HookRevision, Trigger
from backend.app.hooks.schemas import HookWrite
from backend.app.jobs.models import Job
from backend.app.telemetry.models import Telemetry
from backend.app.users.models import User
from backend.app.vehicles.models import Vehicle


class HookValidationError(Exception):
    pass


def validate_source(source: str) -> None:
    wrapped = "def __vehinode_hook(ctx):\n" + textwrap.indent(source, "    ")
    try:
        compile(wrapped, "<vehinode-hook>", "exec")
    except SyntaxError as exc:
        raise HookValidationError(f"line {max(1, (exc.lineno or 2) - 1)}: {exc.msg}") from exc


def create_hook(db: Session, creator: User, data: HookWrite) -> Hook:
    validate_source(data.source)
    if data.vehicle_id:
        vehicle = db.scalar(select(Vehicle.id).where(Vehicle.id == data.vehicle_id))
        if not vehicle:
            raise HookValidationError("vehicle filter does not exist")
    hook = Hook(created_by=creator.id, **data.model_dump())
    db.add(hook)
    db.flush()
    db.add(
        HookRevision(
            hook_id=hook.id,
            revision=1,
            source=hook.source,
            created_by=creator.id,
        )
    )
    return hook


def update_hook(db: Session, hook: Hook, editor: User, data: HookWrite) -> Hook:
    validate_source(data.source)
    if data.vehicle_id:
        vehicle = db.scalar(select(Vehicle.id).where(Vehicle.id == data.vehicle_id))
        if not vehicle:
            raise HookValidationError("vehicle filter does not exist")
    changed_source = hook.source != data.source
    for key, value in data.model_dump().items():
        setattr(hook, key, value)
    if changed_source:
        hook.revision += 1
        db.add(
            HookRevision(
                hook_id=hook.id,
                revision=hook.revision,
                source=hook.source,
                created_by=editor.id,
            )
        )
    return hook


def queue_manual_execution(
    db: Session, hook: Hook, telemetry: Telemetry, dry_run: bool
) -> HookExecution:
    trigger = Trigger(
        type="manual.test",
        version=2,
        occurred_at=utcnow(),
        vehicle_id=telemetry.vehicle_id,
        device_id=telemetry.device_id,
        telemetry_id=telemetry.id,
        payload={
            "telemetry_id": telemetry.id,
            "telemetry_ids": [telemetry.id],
            "dry_run": dry_run,
        },
    )
    db.add(trigger)
    db.flush()
    execution = HookExecution(
        hook_id=hook.id,
        trigger_id=trigger.id,
        telemetry_id=telemetry.id,
        dry_run=dry_run,
        status="pending",
    )
    db.add(execution)
    db.flush()
    db.add(Job(type="hook.execute", payload={"execution_id": execution.id}))
    return execution
