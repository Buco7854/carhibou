# Trusted hook runtime

> Users with permission to modify Python hooks have privileged code-execution
> capability in the VehiNode hook execution environment.

Hooks are trusted Python, not a multi-tenant sandbox. Reliability containment uses a
dedicated child process per execution, wall/CPU timeout, memory/file limits, capped
output, crash isolation and sanitized results. Telemetry is already committed before
the worker runs.

## Batch execution

Ingestion queues one execution per hook per accepted batch, not per sample. The trigger
payload carries `telemetry_ids` for the whole batch; the execution stays pinned to the
newest sample so existing foreign keys and the execution list keep working. Rows deleted
between trigger and run are simply absent from the batch.

This keeps a ten-sample upload to one child process and moves the iterate-or-not decision
into hook code, where the author knows whether a side effect belongs to a reading or to a
delivery.

## Context

SDK version 2 exposes immutable `ctx.event`, `ctx.telemetry` (newest sample),
`ctx.telemetry_batch` (all samples, oldest first), `ctx.vehicle` and `ctx.device`;
durable JSON `ctx.state`; encrypted `ctx.secrets`; HTTP, geometry and structured logging
helpers; and `ctx.dry_run`. ORM entities are never exposed. State is serialized only on
success and cannot contain a known plaintext secret. Executions for one hook are
serialized to make state read-modify-write deterministic.

Automatic retries are deliberately absent for arbitrary hook failures because side
effects may not be idempotent. Failed/time-out/crash-recovered executions are visible
and can be manually retried. A dry run is advisory: code must inspect `ctx.dry_run` to
suppress real network requests.
