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

from backend.app.branding import HOOK_SDK_VERSION
from backend.app.common.settings import get_settings
from backend.app.devices.models import Device
from backend.app.hooks.child import RESULT_MARKER
from backend.app.hooks.models import Hook, HookExecution, HookState, Trigger
from backend.app.secrets.crypto import decrypt_secret, redact_text
from backend.app.secrets.models import Secret
from backend.app.telemetry.models import Telemetry
from backend.app.vehicle_state.models import VehicleState
from backend.app.vehicles.models import Vehicle


@dataclass(frozen=True)
class RuntimeResult:
    status: str
    state: dict[str, Any]
    logs: list[dict[str, object]]
    error: str | None


def _position(row: Telemetry | VehicleState) -> dict[str, object] | None:
    if row.latitude is None or row.longitude is None:
        return None
    return {
        "latitude": row.latitude,
        "longitude": row.longitude,
        "altitude": row.altitude,
        "speed": row.gps_speed,
        "heading": row.heading,
        "accuracy": row.accuracy,
    }


def build_runtime_input(
    db: Session, execution: HookExecution
) -> tuple[Hook, dict[str, Any], list[str]]:
    hook = db.get(Hook, execution.hook_id)
    trigger = db.get(Trigger, execution.trigger_id)
    telemetry = db.get(Telemetry, execution.telemetry_id) if execution.telemetry_id else None
    if not hook or not trigger or not telemetry:
        raise LookupError("hook execution inputs no longer exist")
    vehicle = db.get(Vehicle, telemetry.vehicle_id)
    device = db.get(Device, telemetry.device_id)
    if not vehicle or not device:
        raise LookupError("vehicle or device no longer exists")
    current = db.get(VehicleState, vehicle.id)
    state = db.get(HookState, hook.id)
    secret_rows = list(db.scalars(select(Secret).where(Secret.owner_id == hook.owner_id)))
    secrets = {row.name: decrypt_secret(row.encrypted_value) for row in secret_rows}
    data = {
        "sdk_version": HOOK_SDK_VERSION,
        "source": hook.source,
        "dry_run": execution.dry_run,
        "log_limit": get_settings().hook_log_bytes,
        "event": {
            "id": trigger.id,
            "type": trigger.type,
            "version": trigger.version,
            "occurred_at": trigger.occurred_at.isoformat(),
            "vehicle_id": trigger.vehicle_id,
            "device_id": trigger.device_id,
            "payload": trigger.payload,
        },
        "telemetry": {
            "id": telemetry.id,
            "recorded_at": telemetry.recorded_at.isoformat(),
            "position": _position(telemetry),
            "metrics": telemetry.metrics,
            "device": telemetry.device_data,
        },
        "vehicle": {
            "id": vehicle.id,
            "name": vehicle.name,
            "manufacturer": vehicle.manufacturer,
            "model": vehicle.model,
            "state": {
                "updated_at": current.updated_at.isoformat() if current else None,
                "position": _position(current) if current else None,
                "metrics": current.latest_metrics if current else {},
                "device": current.device_state if current else {},
            },
        },
        "device": {
            "id": device.id,
            "name": device.name,
            "agent_version": device.agent_version,
            "hostname": device.hostname,
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
