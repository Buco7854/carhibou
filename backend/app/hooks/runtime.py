import json
import os
import resource
import subprocess
import sys
from dataclasses import dataclass
from tempfile import TemporaryFile
from typing import Any, BinaryIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.agents.models import Agent
from backend.app.branding import HOOK_SDK_VERSION
from backend.app.common.settings import get_settings
from backend.app.common.time import as_utc
from backend.app.connectors.models import Connector
from backend.app.hooks.child import RESULT_MARKER
from backend.app.hooks.models import Hook, HookExecution, HookState, Trigger
from backend.app.secrets.crypto import decrypt_secret, redact_text
from backend.app.secrets.models import Secret
from backend.app.telemetry.models import Telemetry
from backend.app.telemetry.resolution import resolve_vehicle, vehicle_source_online
from backend.app.vehicles.models import Vehicle


@dataclass(frozen=True)
class RuntimeResult:
    status: str
    state: dict[str, Any]
    logs: list[dict[str, object]]
    error: str | None


def _batch(db: Session, trigger: Trigger, latest: Telemetry) -> list[Telemetry]:
    payload = trigger.payload if isinstance(trigger.payload, dict) else {}
    identifiers = payload.get("telemetry_ids")
    if not isinstance(identifiers, list) or not identifiers:
        return [latest]
    rows = list(
        db.scalars(
            select(Telemetry)
            .where(Telemetry.id.in_([str(value) for value in identifiers]))
            .order_by(Telemetry.recorded_at, Telemetry.sequence)
        )
    )
    return rows or [latest]


def _triggering(db: Session, rows: list[Telemetry]) -> list[dict[str, Any]]:
    connector_ids = set(
        db.scalars(select(Connector.id).where(Connector.id.in_({row.agent_id for row in rows})))
    )
    result: list[dict[str, Any]] = []
    for sample in rows:
        source_kind = "connector" if sample.agent_id in connector_ids else "agent"
        for observation in sample.observation_rows:
            result.append(
                {
                    "telemetry_id": sample.id,
                    "key": observation.metric_key,
                    "value": observation.value,
                    "observed_at": as_utc(observation.observed_at).isoformat(),
                    "source_id": sample.agent_id,
                    "source_kind": source_kind,
                    "channel": observation.channel,
                    "method": observation.method,
                }
            )
        position = sample.position_observation
        if position:
            result.append(
                {
                    "telemetry_id": sample.id,
                    "key": "position",
                    "value": position.value,
                    "observed_at": as_utc(position.observed_at).isoformat(),
                    "source_id": sample.agent_id,
                    "source_kind": source_kind,
                    "channel": position.channel,
                    "method": position.method,
                }
            )
    return result


def build_runtime_input(
    db: Session, execution: HookExecution
) -> tuple[Hook, dict[str, Any], list[str]]:
    hook = db.get(Hook, execution.hook_id)
    trigger = db.get(Trigger, execution.trigger_id)
    telemetry = db.get(Telemetry, execution.telemetry_id) if execution.telemetry_id else None
    if not hook or not trigger or not telemetry:
        raise LookupError("hook execution inputs no longer exist")
    batch = _batch(db, trigger, telemetry)
    vehicle = db.get(Vehicle, telemetry.vehicle_id)
    agent = db.get(Agent, telemetry.agent_id)
    if not vehicle or not agent:
        raise LookupError("vehicle or agent no longer exists")
    state = db.get(HookState, hook.id)
    secret_rows = list(db.scalars(select(Secret)))
    secrets = {row.name: decrypt_secret(row.encrypted_value) for row in secret_rows}
    readings, position = resolve_vehicle(db, vehicle.id)
    vehicle_state = vehicle.state
    updated_at = as_utc(vehicle_state.updated_at).isoformat() if vehicle_state else None
    online = vehicle_source_online(
        db,
        vehicle.id,
        get_settings().default_online_threshold_seconds,
    )
    data = {
        "sdk_version": HOOK_SDK_VERSION,
        "source": hook.source,
        "dry_run": execution.dry_run,
        "log_limit": get_settings().hook_log_bytes,
        "database_url": get_settings().database_url,
        "event": {
            "id": trigger.id,
            "type": trigger.type,
            "version": trigger.version,
            "occurred_at": as_utc(trigger.occurred_at).isoformat(),
            "vehicle_id": trigger.vehicle_id,
            "agent_id": trigger.agent_id,
            "payload": trigger.payload,
        },
        "telemetry_context": {
            "vehicle_id": vehicle.id,
            "triggering": _triggering(db, batch),
            "current": {
                "updated_at": updated_at,
                "online": online,
                "readings": readings,
                "position": position,
                "agent": dict(vehicle_state.agent_state) if vehicle_state else {},
            },
        },
        "vehicle": {
            "id": vehicle.id,
            "name": vehicle.name,
            "manufacturer": vehicle.manufacturer,
            "model": vehicle.model,
        },
        "agent": {
            "id": agent.id,
            "name": agent.name,
            "agent_version": agent.agent_version,
            "hostname": agent.hostname,
        },
        "state": state.value if state else {},
        "secrets": secrets,
    }
    return hook, data, list(secrets.values())


def _limits(memory_mb: int, file_bytes: int, cpu_seconds: int) -> None:
    memory = memory_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    resource.setrlimit(resource.RLIMIT_FSIZE, (file_bytes, file_bytes))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
    os.setsid()


def _read_result(output: BinaryIO, limit: int) -> str:
    output.seek(0)
    return output.read(limit).decode(errors="replace")


def run_hook_process(data: dict[str, Any], timeout: int, secrets: list[str]) -> RuntimeResult:
    settings = get_settings()
    max_output = max(settings.hook_log_bytes * 4, 1_000_000)
    with TemporaryFile() as output:
        process = subprocess.Popen(
            [sys.executable, "-m", "backend.app.hooks.child"],
            stdin=subprocess.PIPE,
            stdout=output,
            stderr=output,
            start_new_session=False,
            preexec_fn=lambda: _limits(settings.hook_memory_mb, max_output, timeout + 1),
        )
        try:
            process.communicate(json.dumps(data, default=str).encode(), timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, 9)
            process.wait(timeout=5)
            return RuntimeResult("timeout", data.get("state", {}), [], "execution timed out")
        raw = _read_result(output, max_output)
    marker = raw.rfind(RESULT_MARKER)
    if marker < 0:
        error = redact_text(raw[-settings.hook_log_bytes :], secrets)
        return RuntimeResult("failed", data.get("state", {}), [], error or "child exited")
    try:
        payload = json.loads(raw[marker + len(RESULT_MARKER) :].splitlines()[0])
    except (json.JSONDecodeError, IndexError) as exc:
        return RuntimeResult("failed", data.get("state", {}), [], f"invalid child result: {exc}")
    logs = payload.get("logs", [])
    for record in logs:
        record["message"] = redact_text(str(record.get("message", "")), secrets) or ""
        if "fields" in record:
            record["fields"] = json.loads(
                redact_text(json.dumps(record["fields"], default=str), secrets) or "{}"
            )
    return RuntimeResult(
        status=payload.get("status", "failed"),
        state=payload.get("state", data.get("state", {})),
        logs=logs,
        error=redact_text(payload.get("error"), secrets),
    )
