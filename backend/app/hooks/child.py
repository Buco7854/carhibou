import contextlib
import json
import os
import sys
import textwrap
import traceback
from typing import Any

from backend.app.hooks.context import CappedWriter, HookContext

RESULT_MARKER = "CARHIBOU_RESULT="
MAX_HOOK_STATE_BYTES = 256_000
MAX_HOOK_ERROR_BYTES = 16_000
MEMORY_ERROR_MESSAGE = "hook exceeded its memory limit"
_ERROR_TRUNCATED_SUFFIX = "\n[error truncated]"
_EMERGENCY_RESULT = (
    '\nCARHIBOU_RESULT={"status":"failed","state":{},"logs":[],'
    f'"error":"{MEMORY_ERROR_MESSAGE}"}}\n'
)
_EMERGENCY_RESULT_BYTES = _EMERGENCY_RESULT.encode()


def _bounded_error(error: BaseException, secret_values: list[str]) -> str:
    if isinstance(error, MemoryError):
        return MEMORY_ERROR_MESSAGE
    try:
        value = "".join(traceback.format_exception(error, limit=20))
        for secret in sorted((item for item in secret_values if item), key=len, reverse=True):
            value = value.replace(secret, "[REDACTED]")
        encoded = value.encode(errors="replace")
        if len(encoded) <= MAX_HOOK_ERROR_BYTES:
            return value
        suffix = _ERROR_TRUNCATED_SUFFIX.encode()
        return (
            encoded[: MAX_HOOK_ERROR_BYTES - len(suffix)].decode(errors="ignore")
            + _ERROR_TRUNCATED_SUFFIX
        )
    except MemoryError:
        return MEMORY_ERROR_MESSAGE


def _json_size(value: object, limit: int) -> int:
    size = 0
    encoder = json.JSONEncoder(ensure_ascii=False, separators=(",", ":"))
    for chunk in encoder.iterencode(value):
        size += len(chunk.encode())
        if size > limit:
            return size
    return size


def _failed(
    error: BaseException, logs: list[dict[str, object]], secret_values: list[str]
) -> dict[str, Any]:
    if isinstance(error, MemoryError):
        logs = []
    return {
        "status": "failed",
        "state": {},
        "logs": logs,
        "error": _bounded_error(error, secret_values),
    }


def execute(data: dict[str, Any]) -> dict[str, Any]:
    records: list[dict[str, object]] = []
    secret_values = [str(value) for value in data.get("secrets", {}).values()]
    archive = None
    try:
        archive_path = data.get("_log_archive_path")
        if isinstance(archive_path, str):
            archive = open(archive_path, "w", encoding="utf-8", buffering=1)  # noqa: SIM115
        log_limit = int(data.get("log_limit", 64_000))
        context = HookContext(data, records, log_limit, archive)
        writer = CappedWriter(log_limit, secret_values, context.log.archive_output)
        source = "def __carhibou_hook(ctx):\n" + textwrap.indent(data["source"], "    ")
        namespace: dict[str, Any] = {"__name__": "__carhibou_hook__"}
        with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
            exec(compile(source, "<carhibou-hook>", "exec"), namespace)
            namespace["__carhibou_hook"](context)
        if writer.value:
            context.log.output(writer.value, truncated=writer.truncated)
        state = context.state.snapshot()
        if _json_size(state, MAX_HOOK_STATE_BYTES) > MAX_HOOK_STATE_BYTES:
            raise ValueError("hook state exceeds 256 KB")
        return {"status": "success", "state": state, "logs": records, "error": None}
    except BaseException as error:  # hook failures include SystemExit; worker remains isolated
        return _failed(error, records, secret_values)
    finally:
        if archive is not None:
            with contextlib.suppress(OSError):
                archive.close()


def _write_emergency(output: Any) -> None:
    try:
        output.write(_EMERGENCY_RESULT)
        output.flush()
    except MemoryError:
        os.write(1, _EMERGENCY_RESULT_BYTES)


def _write_result(output: Any, result: dict[str, Any]) -> None:
    try:
        output.write(RESULT_MARKER)
        json.dump(result, output, ensure_ascii=False, separators=(",", ":"), default=str)
        output.write("\n")
        output.flush()
    except MemoryError:
        _write_emergency(output)


def main() -> int:
    output = sys.__stdout__ or sys.stdout
    try:
        data = json.load(sys.stdin)
        result = execute(data)
    except MemoryError:
        _write_emergency(output)
        return 1
    except BaseException as error:
        try:
            result = _failed(error, [], [])
        except MemoryError:
            _write_emergency(output)
            return 1
    _write_result(output, result)
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
