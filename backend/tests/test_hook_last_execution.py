from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session, sessionmaker

from backend.app.common.time import utcnow
from backend.app.hooks.models import HookExecution, Trigger


def _hook(client: TestClient, csrf: str, name: str) -> str:
    response = client.post(
        "/api/v1/hooks",
        headers={"X-CSRF-Token": csrf},
        json={"name": name, "source": "def handle(ctx):\n    pass\n"},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _execution(db: Session, hook_id: str, status: str, minutes_ago: int) -> None:
    at = utcnow() - timedelta(minutes=minutes_ago)
    trigger = Trigger(type="telemetry.received", occurred_at=at, payload={})
    db.add(trigger)
    db.flush()
    db.add(
        HookExecution(
            hook_id=hook_id,
            trigger_id=trigger.id,
            status=status,
            created_at=at,
        )
    )


def test_list_reports_the_newest_execution_per_hook(
    registered: tuple[TestClient, str], db_factory: sessionmaker[Session]
) -> None:
    client, csrf = registered
    ran = _hook(client, csrf, "Has run")
    _hook(client, csrf, "Never run")

    with db_factory() as db:
        # Out of order on purpose: the newest wins, not the last written.
        _execution(db, ran, "succeeded", minutes_ago=30)
        _execution(db, ran, "failed", minutes_ago=4)
        _execution(db, ran, "succeeded", minutes_ago=90)
        db.commit()

    rows = {row["name"]: row for row in client.get("/api/v1/hooks").json()}

    latest = rows["Has run"]["last_execution"]
    assert latest is not None
    assert latest["status"] == "failed"
    assert set(latest) == {"status", "created_at"}

    # A hook that has never run is not a hook whose last run succeeded.
    assert rows["Never run"]["last_execution"] is None


def test_a_hook_that_has_never_run_reports_null_everywhere_it_is_returned(
    registered: tuple[TestClient, str],
) -> None:
    """Create, update and restore all return the same shape, and a hook fresh out
    of create has no runs to report."""
    client, csrf = registered
    created = client.post(
        "/api/v1/hooks",
        headers={"X-CSRF-Token": csrf},
        json={"name": "Fresh", "source": "def handle(ctx):\n    pass\n"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["last_execution"] is None

    edited = client.put(
        f"/api/v1/hooks/{created.json()['id']}",
        headers={"X-CSRF-Token": csrf},
        json={"name": "Fresh", "source": "def handle(ctx):\n    return 1\n"},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["last_execution"] is None


def test_the_list_costs_the_same_number_of_queries_however_many_hooks_there_are(
    registered: tuple[TestClient, str], db_factory: sessionmaker[Session]
) -> None:
    """The point of the window function. A per-hook lookup passes every other
    test in this file and only shows up as a slow page once somebody has written
    a dozen hooks."""
    client, csrf = registered
    engine = db_factory.kw["bind"]
    counted: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def count(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        counted.append(statement)

    def queries_for(hooks: int) -> int:
        for index in range(hooks):
            hook_id = _hook(client, csrf, f"Hook {index} {hooks}")
            with db_factory() as db:
                _execution(db, hook_id, "succeeded", minutes_ago=index + 1)
                db.commit()
        counted.clear()
        assert client.get("/api/v1/hooks").status_code == 200
        return len(counted)

    try:
        one = queries_for(1)
        many = queries_for(6)
    finally:
        event.remove(engine, "before_cursor_execute", count)

    assert many == one, (
        f"listing cost {one} queries with 1 hook and {many} with 7: "
        "the last-execution lookup grows with the hooks"
    )


@pytest.mark.parametrize("status", ["pending", "running", "succeeded", "failed"])
def test_status_is_passed_through_as_stored(
    registered: tuple[TestClient, str], db_factory: sessionmaker[Session], status: str
) -> None:
    client, csrf = registered
    hook_id = _hook(client, csrf, f"Hook {status}")
    with db_factory() as db:
        _execution(db, hook_id, status, minutes_ago=1)
        db.commit()
    rows = client.get("/api/v1/hooks").json()
    assert rows[0]["last_execution"]["status"] == status
