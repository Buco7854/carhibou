import asyncio
from typing import cast

from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.api.events import load_vehicle_snapshot, vehicle_event_stream
from backend.app.auth.models import BrowserSession
from backend.app.common.time import utcnow


class ConnectedRequest:
    async def is_disconnected(self) -> bool:
        return False


def test_vehicle_event_snapshot_is_owned_and_session_bound(
    registered: tuple[TestClient, str], db_factory: sessionmaker[Session]
) -> None:
    client, csrf = registered
    vehicle = client.post(
        "/api/v1/vehicles",
        headers={"X-CSRF-Token": csrf},
        json={"name": "Live C-Zero"},
    )
    assert vehicle.status_code == 201

    with db_factory() as db:
        browser_session = db.scalar(select(BrowserSession))
        assert browser_session is not None
        user_id = browser_session.user_id
        session_id = browser_session.id

    snapshot = load_vehicle_snapshot(db_factory, user_id, session_id)
    assert snapshot is not None
    assert [row["name"] for row in snapshot] == ["Live C-Zero"]

    async def first_event() -> str:
        stream = vehicle_event_stream(
            cast(Request, ConnectedRequest()), db_factory, user_id, session_id
        )
        try:
            return await anext(stream)
        finally:
            await stream.aclose()

    event = asyncio.run(first_event())
    assert "event: vehicle.states" in event
    assert '"type":"vehicle.states"' in event
    assert '"name":"Live C-Zero"' in event

    with db_factory() as db:
        revoked = db.get(BrowserSession, session_id)
        assert revoked is not None
        revoked.revoked_at = utcnow()
        db.commit()
    assert load_vehicle_snapshot(db_factory, user_id, session_id) is None


def test_event_stream_rejects_non_browser_credentials(client: TestClient) -> None:
    stream_response = client.get("/api/openapi.json").json()["paths"]["/api/v1/events/stream"][
        "get"
    ]["responses"]["200"]
    assert "text/event-stream" in stream_response["content"]
    assert client.get("/api/v1/events/stream").status_code == 401
    assert (
        client.get(
            "/api/v1/events/stream", headers={"Authorization": "Device not-a-browser-session"}
        ).status_code
        == 401
    )
