# Trusted Python hooks

A hook is Python that runs in the worker after telemetry has been stored. Save and test
a hook before enabling it.

## One upload, one run

A tracker uploads samples in batches. Each batch runs your hook **once** and gives it the
whole batch, so you decide whether one reading is enough or every row matters:

- `ctx.telemetry` — the newest sample in the batch.
- `ctx.telemetry_batch` — every sample in it, oldest first.

```python
# React to the current state only.
soc = ctx.telemetry.metrics.get("battery.soc")
if soc is not None and soc < 20:
    ctx.log.warning("Battery is low", soc=soc)
```

```python
# Or act on every row the tracker just delivered.
for row in ctx.telemetry_batch:
    ctx.log.info("sample", at=row.recorded_at.isoformat(), metrics=dict(row.metrics))
```

Iterating is a choice, not a cost: a ten-row batch is still one process and one entry in
the execution history.

## What you can import

Hook source is ordinary Python with no import restrictions, so the standard library is
available in full. On top of it the runtime image carries the application's own
dependencies, which a hook may import directly:

`httpx` · `pydantic` · `sqlalchemy` · `cryptography` · `pyyaml` · `pyserial` ·
`psycopg` · `alembic` · `argon2-cffi` · `email-validator` · `dnspython`

There is no `requests`; use `httpx`, or `ctx.http`, which wraps it with a bounded timeout
and redacts secrets from logs.

Anything else has to be in the image before the worker starts. The container runs
read-only, so a hook cannot install a package at runtime and should not try. Build an
image with the extra distributions instead:

```sh
docker build --build-arg VEHINODE_HOOK_PACKAGES="paho-mqtt==2.1.0 influxdb-client==1.49.0" \
  -t my-vehinode .
```

Then point `VEHINODE_IMAGE` at that tag. Pin every version you add: an unpinned name makes
the image unreproducible and widens what you are trusting. The build applies the runtime
lock as a constraint, so a package that would move one of the application's own pinned
dependencies fails the build rather than quietly shipping an untested combination.

## Editing

Pick a hook from the list to edit it. **Test with telemetry** replays the vehicle's most
recent sample as a one-row batch; `ctx.dry_run` is true for those runs, but VehiNode does
not block HTTP, so check the flag yourself when side effects are unsafe.

**Maximum run time** is how long the worker lets a run continue before stopping it. The
telemetry that triggered it is already stored, so this bounds the hook, not ingestion.

Failures and timeouts are recorded and retries are explicit, because side effects are not
assumed to be repeatable. Revisions keep earlier source and can be restored as a new
revision, leaving the audit trail intact.

Secrets are shared by every hook you own, are write-only, and appear masked after saving.

::: danger Privileged capability
Anyone who can edit Python hooks has privileged code execution inside the hook worker.
Process limits protect reliability; they are not a hostile-code sandbox.
:::
