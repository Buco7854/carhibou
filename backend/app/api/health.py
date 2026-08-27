from datetime import timedelta

from fastapi import APIRouter
from sqlalchemy import func, select, text

from backend.app.access.dependencies import RequireAdmin
from backend.app.agents.models import Agent
from backend.app.auth.dependencies import Db
from backend.app.branding import APP_VERSION
from backend.app.common.time import utcnow
from backend.app.hooks.models import HookExecution
from backend.app.jobs.models import Job, WorkerHeartbeat

router = APIRouter(tags=["health"])


@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok", "version": APP_VERSION}


@router.get("/health/ready")
def ready(db: Db) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ready", "database": "ok"}


@router.get("/api/v1/system/diagnostics")
def diagnostics(auth: RequireAdmin, db: Db) -> dict[str, object]:
    del auth
    now = utcnow()
    return {
        "version": APP_VERSION,
        "database": "connected",
        "pending_jobs": db.scalar(select(func.count(Job.id)).where(Job.status == "pending")) or 0,
        "failed_jobs": db.scalar(select(func.count(Job.id)).where(Job.status == "failed")) or 0,
        "hook_failures": db.scalar(
            select(func.count(HookExecution.id)).where(
                HookExecution.status.in_(["failed", "timeout"])
            )
        )
        or 0,
        "stale_agents": db.scalar(
            select(func.count(Agent.id)).where(
                Agent.revoked_at.is_(None),
                (
                    Agent.last_seen_at.is_(None)
                    | (Agent.last_seen_at < now - timedelta(minutes=10))
                ),
            )
        )
        or 0,
        "workers": [
            {"id": row.worker_id, "version": row.version, "seen_at": row.seen_at}
            for row in db.scalars(select(WorkerHeartbeat).order_by(WorkerHeartbeat.worker_id))
        ],
    }
