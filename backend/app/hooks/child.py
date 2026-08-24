import contextlib
import json
import sys
import textwrap
import traceback
from typing import Any

from backend.app.hooks.context import CappedWriter, HookContext

RESULT_MARKER = "VEHINODE_RESULT="


def execute(data: dict[str, Any]) -> dict[str, Any]:
    records: list[dict[str, object]] = []
    context = HookContext(data, records)
    writer = CappedWriter(int(data.get("log_limit", 64_000)))
    source = "def __vehinode_hook(ctx):\n" + textwrap.indent(data["source"], "    ")
    namespace: dict[str, Any] = {"__name__": "__vehinode_hook__"}
    try:
        with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):  # type: ignore[type-var]
            exec(compile(source, "<vehinode-hook>", "exec"), namespace)
            namespace["__vehinode_hook"](context)
        if writer.value:
            records.append(
                {
                    "level": "output",
                    "message": writer.value,
                    "truncated": writer.truncated,
                }
            )
        state = context.state.snapshot()
        encoded_state = json.dumps(state)
        if len(encoded_state.encode()) > 256_000:
            raise ValueError("hook state exceeds 256 KB")
        return {"status": "success", "state": state, "logs": records, "error": None}
    except BaseException:  # hook failures include SystemExit; worker remains isolated
        return {
            "status": "failed",
            "state": data.get("state", {}),
            "logs": records,
            "error": traceback.format_exc(limit=20),
        }


def main() -> int:
    try:
        data = json.load(sys.stdin)
        result = execute(data)
    except BaseException:
        result = {
            "status": "failed",
            "state": {},
            "logs": [],
            "error": traceback.format_exc(limit=20),
        }
    output = sys.__stdout__ or sys.stdout
    output.write(RESULT_MARKER + json.dumps(result, default=str) + "\n")
    output.flush()
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
