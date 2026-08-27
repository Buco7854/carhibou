from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.app.common.settings import get_settings
from backend.app.common.time import utcnow
from backend.app.hooks.models import HookExecution
from backend.app.jobs.models import Job

# Hook timeouts are capped at 120 seconds. The lease deliberately exceeds that
# maximum so a healthy, long-running hook is never mistaken for a crashed worker.
LEASE_SECONDS = 180


def recover_expired_leases(db: Session) -> int:
    cutoff = utcnow() - timedelta(seconds=LEASE_SECONDS)
    stale = list(
        db.scalars(
            select(Job).where(Job.status == "running", Job.locked_at < cutoff).with_for_update()
        )
    )
    for job in stale:
        job.status = "failed"
        job.last_error = "worker lease expired; manual retry required"
        job.completed_at = utcnow()
        execution_id = job.payload.get("execution_id")
        if job.type == "hook.execute" and isinstance(execution_id, str):
            execution = db.get(HookExecution, execution_id)
            if execution and execution.status == "running":
                execution.status = "failed"
                execution.error = job.last_error
                execution.finished_at = utcnow()
    return len(stale)


def claim_job(db: Session) -> Job | None:
    recover_expired_leases(db)
    job = db.scalar(
        select(Job)
        .where(
            Job.status == "pending",
            Job.next_attempt_at <= utcnow(),
            or_(
                Job.locked_at.is_(None),
                Job.locked_at < utcnow() - timedelta(seconds=LEASE_SECONDS),
            ),
        )
        .order_by(Job.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job:
        job.status = "running"
        job.locked_at = utcnow()
        job.locked_by = get_settings().worker_id
        job.attempts += 1
    return job
