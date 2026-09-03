import io
import json
from typing import Any

import pytest

from backend.app.hooks.child import (
    MAX_HOOK_ERROR_BYTES,
    MEMORY_ERROR_MESSAGE,
    RESULT_MARKER,
    _write_result,
)
from backend.app.hooks.context import MAX_LOG_RECORDS
from backend.app.hooks.runtime import run_hook_process


def _runtime_input(source: str, *, log_limit: int = 4096) -> dict[str, Any]:
    return {
        "sdk_version": 3,
        "source": source,
        "dry_run": False,
        "log_limit": log_limit,
        "database_url": "sqlite://",
        "event": {
            "id": "event-1",
            "type": "telemetry.received",
            "version": 2,
            "occurred_at": "2026-09-03T12:00:00+00:00",
            "vehicle_id": "vehicle-1",
            "agent_id": "agent-1",
            "payload": {},
        },
        "telemetry_context": {
            "vehicle_id": "vehicle-1",
            "triggering": [],
            "current": {
                "updated_at": None,
                "online": False,
                "readings": {},
                "position": None,
                "agent": {},
            },
        },
        "vehicle": {
            "id": "vehicle-1",
            "name": "Car",
            "manufacturer": None,
            "model": None,
        },
        "agent": {
            "id": "agent-1",
            "name": "Agent",
            "agent_version": "test",
            "hostname": "pi",
        },
        "state": {},
        "secrets": {},
    }


def test_many_structured_logs_produce_a_bounded_serializable_result() -> None:
    log_limit = 4096
    archived: list[dict[str, object]] = []
    result = run_hook_process(
        _runtime_input(
            'for index in range(10_000):\n    ctx.log.info("Forwarded position", index=index)',
            log_limit=log_limit,
        ),
        timeout=10,
        secrets=[],
        log_sink=archived.extend,
    )

    assert result.status == "success", result.error
    assert result.log_count == 10_000
    assert result.logs_truncated is True
    assert len(archived) == 10_000
    assert archived[-1]["fields"] == {"index": 9999}
    assert len(result.logs) <= MAX_LOG_RECORDS
    marker = result.logs[-1]
    assert marker["truncated"] is True
    assert "hook log entries omitted from preview" in str(marker["message"])
    assert int(marker["fields"]["omitted"]) > 0  # type: ignore[index]
    encoded = json.dumps(
        {
            "status": result.status,
            "state": result.state,
            "logs": result.logs,
            "error": result.error,
        }
    )
    assert len(encoded.encode()) < log_limit + 1024


def test_one_log_per_bounded_trigger_sample_remains_fully_visible() -> None:
    result = run_hook_process(
        _runtime_input(
            "for index in range(200):\n"
            '    ctx.log.info("Forwarded position to Traccar", '
            'id="vehicle-1", lat=48.8, lon=2.3, timestamp=index)',
            log_limit=64_000,
        ),
        timeout=10,
        secrets=[],
    )

    assert result.status == "success", result.error
    assert result.log_count == 200
    assert result.logs_truncated is False
    assert len(result.logs) == 200
    assert all(record.get("truncated") is not True for record in result.logs)
    assert all(record["message"] == "Forwarded position to Traccar" for record in result.logs)


def test_memory_error_becomes_a_small_clean_failure() -> None:
    result = run_hook_process(
        _runtime_input("raise MemoryError"),
        timeout=10,
        secrets=[],
    )
    assert result.status == "failed"
    assert result.log_count == 0
    assert result.logs == []
    assert result.error == MEMORY_ERROR_MESSAGE


def test_error_text_is_bounded_before_result_serialization() -> None:
    result = run_hook_process(
        _runtime_input('raise RuntimeError("x" * 100_000)'),
        timeout=10,
        secrets=[],
    )
    assert result.status == "failed"
    assert result.error is not None
    assert len(result.error.encode()) <= MAX_HOOK_ERROR_BYTES
    assert result.error.endswith("[error truncated]")


def test_result_writer_has_a_constant_memory_error_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = io.StringIO()

    def fail_dump(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise MemoryError

    monkeypatch.setattr("backend.app.hooks.child.json.dump", fail_dump)
    _write_result(output, {"status": "success", "state": {}, "logs": [], "error": None})

    raw = output.getvalue()
    marker = raw.rfind(RESULT_MARKER)
    payload = json.loads(raw[marker + len(RESULT_MARKER) :].splitlines()[0])
    assert payload == {
        "status": "failed",
        "state": {},
        "logs": [],
        "error": MEMORY_ERROR_MESSAGE,
    }
