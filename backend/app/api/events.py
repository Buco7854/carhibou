import asyncio
import hashlib
import json
import logging
import time
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, sessionmaker

from backend.app.auth.dependencies import CurrentUser, Db
from backend.app.auth.models import BrowserSession
from backend.app.common.time import as_utc, utcnow
from backend.app.users.models import User
from backend.app.vehicles.services import list_vehicles, serialize_vehicle

router = APIRouter(prefix="/events", tags=["events"])
logger = logging.getLogger(__name__)

POLL_SECONDS = 1.0
KEEPALIVE_SECONDS = 15.0


def load_vehicle_snapshot(
    factory: sessionmaker[Session], user_id: str, session_id: str
) -> list[dict[str, object]] | None:
    """Return current owned-vehicle state, or None when the browser session is invalid."""
    with factory() as db:
        browser_session = db.get(BrowserSession, session_id)
        user = db.get(User, user_id)
        now = utcnow()
        if (
            not browser_session
            or browser_session.user_id != user_id
            or browser_session.revoked_at is not None
            or as_utc(browser_session.expires_at) < now
            or not user
            or not user.is_active
        ):
            return None
        return [
            serialize_vehicle(vehicle).model_dump(mode="json")
            for vehicle in list_vehicles(db, user_id)
        ]


def format_sse(event: str, data: dict[str, object], event_id: str | None = None) -> str:
    lines = []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    lines.append(f"data: {json.dumps(data, separators=(',', ':'), ensure_ascii=False)}")
    return "\n".join(lines) + "\n\n"


async def vehicle_event_stream(
    request: Request,
    factory: sessionmaker[Session],
    user_id: str,
    session_id: str,
) -> AsyncGenerator[str, None]:
    previous_digest = ""
    last_sent_at = time.monotonic()
    while not await request.is_disconnected():
        try:
            vehicles = await asyncio.to_thread(load_vehicle_snapshot, factory, user_id, session_id)
        except Exception:
            logger.exception("browser event stream snapshot failed", extra={"user_id": user_id})
            return
        if vehicles is None:
            yield format_sse(
                "session.expired",
                {"type": "session.expired", "version": 1, "occurred_at": utcnow().isoformat()},
            )
            return

        canonical = json.dumps(vehicles, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        now = time.monotonic()
        if digest != previous_digest:
            yield format_sse(
                "vehicle.states",
                {
                    "type": "vehicle.states",
                    "version": 1,
                    "occurred_at": utcnow().isoformat(),
                    "vehicles": vehicles,
                },
                digest,
            )
            previous_digest = digest
            last_sent_at = now
        elif now - last_sent_at >= KEEPALIVE_SECONDS:
            yield ": keepalive\n\n"
            last_sent_at = now
        await asyncio.sleep(POLL_SECONDS)


@router.get(
    "/stream",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Versioned live events for the authenticated browser session",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        }
    },
)
def stream_events(request: Request, db: Db, auth: CurrentUser) -> StreamingResponse:
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    return StreamingResponse(
        vehicle_event_stream(request, factory, auth.user.id, auth.session.id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
