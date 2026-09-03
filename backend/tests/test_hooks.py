from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.auth.services import create_local_user
from backend.app.common.time import utcnow
from backend.app.hooks.models import HookExecution, HookExecutionLog, HookState, Trigger
from backend.app.jobs.models import Job
from backend.app.jobs.services import LEASE_SECONDS, recover_expired_leases
from backend.app.worker import execute_hook_job


def _prepare_agent(client: TestClient, csrf: str) -> tuple[str, str]:
    vehicle = client.post(
        "/api/v1/vehicles",
        headers={"X-CSRF-Token": csrf},
        json={"name": "Hook car"},
    ).json()
    token = client.post(
        f"/api/v1/vehicles/{vehicle['id']}/enrollments",
        headers={"X-CSRF-Token": csrf},
        json={"implementation_id": "custom", "name": "Simulator"},
    ).json()["token"]
    credential = client.post(
        "/api/v1/agent/enroll",
        json={
            "token": token,
            "implementation_id": "custom",
            "protocol_version": 2,
            "agent_version": "test",
            "hostname": "sim",
        },
    ).json()["credential"]
    return vehicle["id"], credential


def _send_sample(client: TestClient, credential: str) -> str:
    sample_id = str(uuid4())
    observed_at = datetime.now(UTC).isoformat()
    response = client.post(
        "/api/v1/agent/telemetry/batch",
        headers={"Authorization": f"Agent {credential}"},
        json={
            "boot_id": str(uuid4()),
            "samples": [
                {
                    "id": sample_id,
                    "sequence": 1,
                    "recorded_at": observed_at,
                    "position": {
                        "value": {"latitude": 48.0, "longitude": 2.0},
                        "observed_at": observed_at,
                        "channel": "gnss",
                        "method": "direct",
                    },
                    "observations": [
                        {
                            "key": "battery.soc",
                            "value": 25,
                            "observed_at": observed_at,
                            "channel": "can",
                            "method": "direct",
                        }
                    ],
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    return sample_id


def _send_batch(client: TestClient, credential: str, soc_values: list[float]) -> list[str]:
    base = datetime.now(UTC)
    identifiers = [str(uuid4()) for _ in soc_values]
    response = client.post(
        "/api/v1/agent/telemetry/batch",
        headers={"Authorization": f"Agent {credential}"},
        json={
            "boot_id": str(uuid4()),
            "samples": [
                {
                    "id": identifier,
                    "sequence": index,
                    "recorded_at": (base + timedelta(seconds=index)).isoformat(),
                    "observations": [
                        {
                            "key": "battery.soc",
                            "value": soc,
                            "observed_at": (base + timedelta(seconds=index)).isoformat(),
                            "channel": "can",
                            "method": "direct",
                        }
                    ],
                }
                for index, (identifier, soc) in enumerate(zip(identifiers, soc_values, strict=True))
            ],
        },
    )
    assert response.status_code == 200, response.text
    return identifiers


def _run_pending(db_factory: sessionmaker[Session]) -> HookExecution:
    with db_factory() as db:
        job = db.scalar(select(Job).where(Job.status == "pending").order_by(Job.created_at))
        assert job is not None
        job.status = "running"
        db.commit()
        execute_hook_job(db, job)
        db.commit()
        execution = db.scalar(
            select(HookExecution).where(HookExecution.id == job.payload["execution_id"])
        )
        assert execution is not None
        return execution


def test_telemetry_hook_runs_outside_request_persists_state_and_redacts_secrets(
    registered: tuple[TestClient, str], db_factory: sessionmaker[Session]
) -> None:
    client, csrf = registered
    _vehicle_id, credential = _prepare_agent(client, csrf)
    secret = client.put(
        "/api/v1/secrets/api_token",
        headers={"X-CSRF-Token": csrf},
        json={"name": "api_token", "value": "super-secret-value"},
    )
    assert secret.status_code == 200
    assert "super-secret-value" not in secret.text
    hook = client.post(
        "/api/v1/hooks",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": "Counter",
            "enabled": True,
            "source": (
                'ctx.state["count"] = ctx.state.get("count", 0) + 1\n'
                'ctx.state["soc"] = ctx.telemetry.current.readings["battery.soc"].value\n'
                'ctx.log.info("token=" + ctx.secrets["api_token"])\n'
                'print(ctx.secrets["api_token"])'
            ),
        },
    )
    assert hook.status_code == 201, hook.text

    _send_sample(client, credential)
    # The API only enqueued work; execution remains pending until a worker runs it.
    before = client.get(f"/api/v1/hooks/{hook.json()['id']}/executions").json()
    assert before[0]["status"] == "pending"
    execution = _run_pending(db_factory)
    assert execution.status == "success"
    assert "super-secret-value" not in str(execution.logs)
    assert "[REDACTED]" in str(execution.logs)
    with db_factory() as db:
        archived_logs = list(
            db.scalars(
                select(HookExecutionLog).where(HookExecutionLog.execution_id == execution.id)
            )
        )
        assert "super-secret-value" not in str([row.record for row in archived_logs])
        assert "[REDACTED]" in str([row.record for row in archived_logs])
        state = db.get(HookState, hook.json()["id"])
        assert state is not None
        assert state.value == {"count": 1, "soc": 25}


def test_hook_timeout_and_revision_history(
    registered: tuple[TestClient, str], db_factory: sessionmaker[Session]
) -> None:
    client, csrf = registered
    _vehicle_id, credential = _prepare_agent(client, csrf)
    hook = client.post(
        "/api/v1/hooks",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": "Runaway",
            "enabled": True,
            "timeout_seconds": 1,
            "source": "while True:\n    pass",
        },
    )
    assert hook.status_code == 201
    _send_sample(client, credential)
    execution = _run_pending(db_factory)
    assert execution.status == "timeout"
    assert execution.error == "execution timed out"

    updated = client.put(
        f"/api/v1/hooks/{hook.json()['id']}",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": "Runaway fixed",
            "enabled": False,
            "timeout_seconds": 1,
            "source": 'ctx.log.info("fixed")',
        },
    )
    assert updated.json()["revision"] == 2
    revisions = client.get(f"/api/v1/hooks/{hook.json()['id']}/revisions").json()
    assert [row["revision"] for row in revisions] == [2, 1]
    restored = client.post(
        f"/api/v1/hooks/{hook.json()['id']}/revisions/1/restore",
        headers={"X-CSRF-Token": csrf},
    )
    assert restored.status_code == 200
    assert restored.json()["revision"] == 3
    assert restored.json()["source"] == "while True:\n    pass"


def test_non_admin_cannot_manage_hook_code(
    registered: tuple[TestClient, str], db_factory: sessionmaker[Session]
) -> None:
    client, _csrf = registered
    with db_factory() as db:
        create_local_user(
            db,
            "second@example.com",
            "another-long-test-password",
            "Second",
            admin=False,
        )
        db.commit()
    second = client.post(
        "/api/v1/auth/login",
        json={"email": "second@example.com", "password": "another-long-test-password"},
    )
    csrf = second.json()["csrf_token"]
    denied = client.post(
        "/api/v1/hooks",
        headers={"X-CSRF-Token": csrf},
        json={"name": "Forbidden", "source": "pass"},
    )
    assert denied.status_code == 403


def test_secret_value_cannot_be_persisted_as_plaintext_hook_state(
    registered: tuple[TestClient, str], db_factory: sessionmaker[Session]
) -> None:
    client, csrf = registered
    _vehicle_id, credential = _prepare_agent(client, csrf)
    client.put(
        "/api/v1/secrets/private_value",
        headers={"X-CSRF-Token": csrf},
        json={"name": "private_value", "value": "must-remain-encrypted"},
    )
    hook = client.post(
        "/api/v1/hooks",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": "Accidental leak",
            "enabled": True,
            "source": 'ctx.state["copied"] = ctx.secrets["private_value"]',
        },
    )
    _send_sample(client, credential)
    execution = _run_pending(db_factory)
    assert execution.status == "failed"
    assert execution.error == "hook state contains a secret value and was not persisted"
    with db_factory() as db:
        assert db.get(HookState, hook.json()["id"]) is None


def test_expired_worker_lease_is_failed_for_manual_retry(
    registered: tuple[TestClient, str], db_factory: sessionmaker[Session]
) -> None:
    client, csrf = registered
    _vehicle_id, credential = _prepare_agent(client, csrf)
    client.post(
        "/api/v1/hooks",
        headers={"X-CSRF-Token": csrf},
        json={"name": "Crash recovery", "enabled": True, "source": "pass"},
    )
    _send_sample(client, credential)
    with db_factory() as db:
        job = db.scalar(select(Job).where(Job.status == "pending"))
        assert job is not None
        execution = db.get(HookExecution, job.payload["execution_id"])
        assert execution is not None
        job.status = "running"
        job.locked_at = utcnow() - timedelta(seconds=LEASE_SECONDS + 1)
        execution.status = "running"
        db.commit()
        assert recover_expired_leases(db) == 1
        db.commit()
        assert job.status == "failed"
        assert execution.status == "failed"
        assert "manual retry" in (execution.error or "")


def test_one_batch_queues_one_execution_that_can_iterate_every_sample(
    registered: tuple[TestClient, str], db_factory: sessionmaker[Session]
) -> None:
    client, csrf = registered
    _vehicle_id, credential = _prepare_agent(client, csrf)
    hook = client.post(
        "/api/v1/hooks",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": "Batch reader",
            "enabled": True,
            "source": (
                'ctx.state["runs"] = ctx.state.get("runs", 0) + 1\n'
                'ctx.state["seen"] = [row.value for row in ctx.telemetry.triggering '
                'if row.key == "battery.soc"]\n'
                'ctx.state["latest"] = ctx.telemetry.current.readings["battery.soc"].value'
            ),
        },
    )
    assert hook.status_code == 201, hook.text

    _send_batch(client, credential, [80, 60, 40])
    with db_factory() as db:
        pending = list(db.scalars(select(Job).where(Job.status == "pending")))
        # Ten rows must not mean ten child processes: the batch is one execution.
        assert len(pending) == 1

    execution = _run_pending(db_factory)
    assert execution.status == "success", execution.error
    with db_factory() as db:
        state = db.get(HookState, hook.json()["id"])
        assert state is not None
        assert state.value == {"runs": 1, "seen": [80, 60, 40], "latest": 40}


def test_large_ingest_splits_hook_triggers_into_bounded_batches(
    registered: tuple[TestClient, str], db_factory: sessionmaker[Session]
) -> None:
    client, csrf = registered
    _vehicle_id, credential = _prepare_agent(client, csrf)
    hook = client.post(
        "/api/v1/hooks",
        headers={"X-CSRF-Token": csrf},
        json={"name": "Bounded batches", "enabled": True, "source": "pass"},
    )
    assert hook.status_code == 201, hook.text

    identifiers = _send_batch(client, credential, [float(index % 101) for index in range(450)])
    with db_factory() as db:
        triggers = list(db.scalars(select(Trigger).order_by(Trigger.occurred_at)))
        jobs = list(db.scalars(select(Job).where(Job.status == "pending")))

    trigger_ids = [
        [str(value) for value in trigger.payload["telemetry_ids"]] for trigger in triggers
    ]
    assert [len(values) for values in trigger_ids] == [200, 200, 50]
    assert [value for values in trigger_ids for value in values] == identifiers
    assert len(jobs) == 3


def test_complete_hook_log_is_available_in_bounded_pages(
    registered: tuple[TestClient, str], db_factory: sessionmaker[Session]
) -> None:
    client, csrf = registered
    _vehicle_id, credential = _prepare_agent(client, csrf)
    hook = client.post(
        "/api/v1/hooks",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": "Full logs",
            "enabled": True,
            "source": ('for index in range(400):\n    ctx.log.info("Archived entry", index=index)'),
        },
    )
    assert hook.status_code == 201, hook.text
    _send_sample(client, credential)
    execution = _run_pending(db_factory)

    assert execution.log_count == 400
    assert execution.logs_truncated is True
    page = client.get(
        f"/api/v1/hooks/executions/{execution.id}/logs",
        params={"limit": 150, "offset": 300},
    )
    assert page.status_code == 200, page.text
    assert page.json()["total"] == 400
    assert len(page.json()["logs"]) == 100
    assert page.json()["logs"][0]["fields"] == {"index": 300}
    assert page.json()["logs"][-1]["fields"] == {"index": 399}


def test_manual_test_run_exposes_a_single_sample_batch(
    registered: tuple[TestClient, str], db_factory: sessionmaker[Session]
) -> None:
    client, csrf = registered
    _vehicle_id, credential = _prepare_agent(client, csrf)
    sample_id = _send_sample(client, credential)
    hook = client.post(
        "/api/v1/hooks",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": "Manual batch",
            "enabled": False,
            "source": (
                'ctx.state["size"] = len({row.telemetry_id for row in ctx.telemetry.triggering})'
            ),
        },
    )
    assert hook.status_code == 201, hook.text
    queued = client.post(
        f"/api/v1/hooks/{hook.json()['id']}/test",
        headers={"X-CSRF-Token": csrf},
        json={"telemetry_id": sample_id, "dry_run": True},
    )
    assert queued.status_code == 200, queued.text

    execution = _run_pending(db_factory)
    assert execution.status == "success", execution.error
    with db_factory() as db:
        state = db.get(HookState, hook.json()["id"])
        assert state is not None
        assert state.value == {"size": 1}
