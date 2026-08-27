import argparse
import json
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from backend.app.branding import APP_VERSION
from backend.app.common import model_registry  # noqa: F401
from backend.app.common.database import SessionLocal
from backend.app.common.logging import configure_logging
from backend.app.common.settings import get_settings
from backend.app.common.time import utcnow
from backend.app.connectors.runtime import ConnectorSupervisor
from backend.app.hooks.models import HookExecution, HookState
from backend.app.hooks.runtime import build_runtime_input, run_hook_process
from backend.app.jobs.models import Job, WorkerHeartbeat
from backend.app.jobs.services import claim_job

logger = logging.getLogger(__name__)


@contextmanager
def hook_state_lock(db: Session, hook_id: str) -> Iterator[None]:
    """Serialize executions per hook so read-modify-write state is deterministic."""
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        yield
        return

    # The ORM session intentionally commits before the child starts, which may
    # return its DBAPI connection to the pool. Keep the session-scoped advisory
    # lock on a dedicated connection so acquisition and release cannot move to
    # different pooled connections while the hook runs.
    engine = bind.engine if isinstance(bind, Connection) else bind
    with engine.connect() as lock_connection:
        lock_connection.execute(
            text("SELECT pg_advisory_lock(hashtext(:hook_id))"), {"hook_id": hook_id}
        )
        try:
            yield
        finally:
            lock_connection.execute(
                text("SELECT pg_advisory_unlock(hashtext(:hook_id))"), {"hook_id": hook_id}
            )


def _contains_secret(value: Any, secrets: list[str]) -> bool:
    if isinstance(value, str):
        return any(secret and secret in value for secret in secrets)
    if isinstance(value, dict):
        return any(
            _contains_secret(key, secrets) or _contains_secret(item, secrets)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_secret(item, secrets) for item in value)
    return False


def heartbeat(db: Session) -> None:
    worker_id = get_settings().worker_id
    model = db.get(WorkerHeartbeat, worker_id)
    if model:
        model.seen_at = utcnow()
        model.version = APP_VERSION
    else:
        db.add(WorkerHeartbeat(worker_id=worker_id, version=APP_VERSION, seen_at=utcnow()))


def execute_hook_job(db: Session, job: Job) -> None:
    execution_id = job.payload.get("execution_id")
    if not isinstance(execution_id, str):
        raise ValueError("hook job has no execution_id")
    execution = db.scalar(
        select(HookExecution).where(HookExecution.id == execution_id).with_for_update()
    )
    if not execution:
        raise LookupError("hook execution no longer exists")
    if execution.status not in {"pending", "running"}:
        job.status = "completed"
        job.completed_at = utcnow()
        return
    # The dedicated advisory-lock connection remains checked out across the
    # intentional commit before the child runs. PostgreSQL releases it if the
    # worker crashes and its connection closes. SQLite tests run serially.
    hook_id = execution.hook_id
    with hook_state_lock(db, hook_id):
        hook, data, secrets = build_runtime_input(db, execution)
        execution.status = "running"
        execution.started_at = utcnow()
        db.commit()

        started = time.monotonic()
        result = run_hook_process(data, hook.timeout_seconds, secrets)
        finished = utcnow()

        execution = db.get(HookExecution, execution_id)
        fresh_job = db.get(Job, job.id)
        if not execution or not fresh_job:
            raise LookupError("execution state disappeared")
        execution.status = result.status
        execution.logs = result.logs
        execution.error = result.error
        execution.finished_at = finished
        execution.duration_seconds = time.monotonic() - started
        if result.status == "success" and _contains_secret(result.state, secrets):
            execution.status = "failed"
            execution.error = "hook state contains a secret value and was not persisted"
        elif result.status == "success":
            # Verify JSON compatibility before assigning to a JSONB column so a
            # serialization error cannot surface after the job is acknowledged.
            json.dumps(result.state)
            state = db.get(HookState, hook.id)
            if state:
                state.value = result.state
                state.version += 1
                state.updated_at = finished
            else:
                db.add(HookState(hook_id=hook.id, value=result.state, updated_at=finished))
        fresh_job.status = "completed"
        fresh_job.completed_at = finished
        fresh_job.locked_at = None
        fresh_job.locked_by = None


def process_one() -> bool:
    with SessionLocal() as db:
        heartbeat(db)
        job = claim_job(db)
        db.commit()
        if not job:
            return False
        try:
            if job.type == "hook.execute":
                execute_hook_job(db, job)
            else:
                raise ValueError(f"unknown job type: {job.type}")
            db.commit()
        except Exception as exc:
            db.rollback()
            failed = db.get(Job, job.id)
            if failed:
                failed.status = "failed"
                failed.last_error = str(exc)[:4000]
                failed.completed_at = utcnow()
            execution_id = job.payload.get("execution_id")
            if isinstance(execution_id, str):
                execution = db.get(HookExecution, execution_id)
                if execution and execution.status in {"pending", "running"}:
                    execution.status = "failed"
                    execution.error = str(exc)[:4000]
                    execution.finished_at = utcnow()
            db.commit()
            logger.exception("job failed", extra={"job_id": job.id})
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Carhibou PostgreSQL job worker")
    parser.add_argument("--once", action="store_true", help="process at most one job")
    args = parser.parse_args()
    configure_logging(get_settings().log_level)
    if args.once:
        process_one()
        return
    supervisor = ConnectorSupervisor(SessionLocal)
    supervisor.start()
    try:
        while True:
            if not process_one():
                time.sleep(1)
    finally:
        supervisor.stop()
        supervisor.join(10)


if __name__ == "__main__":
    main()
