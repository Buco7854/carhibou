# Trusted hook runtime

> Users with permission to modify Python hooks have privileged code-execution
> capability in the VehiNode hook execution environment.

Hooks are trusted Python, not a multi-tenant sandbox. Reliability containment uses a
dedicated child process per execution, wall/CPU timeout, memory/file limits, capped
output, crash isolation and sanitized results. Telemetry is already committed before
the worker runs.

The versioned context exposes immutable `ctx.event`, `ctx.telemetry`, `ctx.vehicle` and
`ctx.device`; durable JSON `ctx.state`; encrypted `ctx.secrets`; HTTP, geometry and
structured logging helpers; and `ctx.dry_run`. ORM entities are never exposed. State is
serialized only on success and cannot contain a known plaintext secret. Executions for
one hook are serialized to make state read-modify-write deterministic.

Automatic retries are deliberately absent for arbitrary hook failures because side
effects may not be idempotent. Failed/time-out/crash-recovered executions are visible
and can be manually retried. A dry run is advisory: code must inspect `ctx.dry_run` to
suppress real network requests.
