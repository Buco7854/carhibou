# Trusted Python hooks

A hook is privileged Python that the worker runs after telemetry is stored. Save and test
it before enabling it. Process limits contain failures for reliability; they are not a
sandbox against an administrator who can edit the source.

![The hooks workspace](/screens/hooks.png)

One uploaded batch produces one run. `ctx.telemetry` is its newest sample, while
`ctx.telemetry_batch` contains every accepted sample oldest first. The context also
provides immutable event, vehicle and device data, durable JSON `ctx.state`, encrypted
`ctx.secrets`, HTTP and geometry helpers, structured logging, and `ctx.dry_run`.

State is written only after success, and executions for one hook are serialized so
read-modify-write is deterministic. Failures and timeouts remain visible and require an
explicit retry because an external side effect may already have happened. Revisions keep
old source available without rewriting the audit trail.

## Secrets and dependencies

Secrets are instance-wide, administrator-managed and write-only. Access one as
`ctx.secrets["name"]`. Stored values are encrypted under `CARHIBOU_MASTER_KEY`; logs and
tracebacks are redacted against current values, but privileged code can still transmit
them. Back up the master key with the database or the values cannot be recovered.

The standard library and application dependencies, including `httpx`, are available.
Prefer bounded `ctx.http` calls because they inherit secret redaction. Extra packages
must be pinned into a custom image before the worker starts:

```sh
docker build --build-arg CARHIBOU_HOOK_PACKAGES="paho-mqtt==2.1.0" -t my-carhibou .
```

Set `CARHIBOU_IMAGE=my-carhibou`. A read-only runtime cannot install packages during a
hook execution.

**Test with telemetry** replays the newest sample as a one-row batch and sets
`ctx.dry_run`. Dry-run behavior is advisory: every side-effecting hook must check it.

## Worked examples

These examples use transitions and persistent state so an event is not repeated for
every reading.

### Low state of charge

```python
soc = ctx.telemetry.metrics.get("battery.soc")
if not isinstance(soc, (int, float)):
    return

armed = ctx.state.get("armed", True)
if armed and soc < 20:
    ctx.log.warning("Battery SOC is low", soc=soc, vehicle=ctx.vehicle.name)
    ctx.state["armed"] = False
elif not armed and soc > 23:
    ctx.state["armed"] = True
```

The 23% re-arm threshold prevents a hovering value from producing repeated alerts.

### Charging finished

Store a `notify_url` secret. An explicit profile signal wins; otherwise negative pack
power means the battery is absorbing energy.

```python
metrics = ctx.telemetry.metrics
declared = metrics.get("charging.active")
power = metrics.get("battery.power")
if isinstance(declared, bool):
    charging = declared
elif isinstance(power, (int, float)):
    charging = power < 0
else:
    return

was_charging = ctx.state.get("charging", False)
ctx.state["charging"] = charging
if was_charging and not charging and not ctx.dry_run:
    ctx.http.post(ctx.secrets["notify_url"], json={
        "text": f"{ctx.vehicle.name} finished charging"
    }, timeout=8)
```

### Gate on arrival

Store `gate_url` and `gate_token`, then replace the demonstration coordinates:

```python
position = ctx.telemetry.position
if position is None:
    return

inside = ctx.geo.within_radius(
    position.latitude, position.longitude, 48.8566, 2.3522, 80
)
was_inside = ctx.state.get("inside_home", False)
if inside and not was_inside and not ctx.dry_run:
    ctx.http.post(ctx.secrets["gate_url"], headers={
        "Authorization": f"Bearer {ctx.secrets['gate_token']}"
    }, timeout=5)
ctx.state["inside_home"] = inside
```

The receiving gate still needs its own authentication, replay protection and safe
operating policy.

### Forward buffered positions to Traccar

Store the complete OsmAnd endpoint as `traccar_url`. Iterating the batch preserves every
point collected while the agent was offline.

```python
if ctx.dry_run:
    return

for row in ctx.telemetry_batch:
    if row.position is None:
        continue
    ctx.http.get(ctx.secrets["traccar_url"], params={
        "id": ctx.vehicle.id,
        "lat": row.position.latitude,
        "lon": row.position.longitude,
        "speed": row.position.speed,
        "bearing": row.position.heading,
        "timestamp": int(row.recorded_at.timestamp()),
    }, timeout=8)
```

A manual retry can duplicate a side effect, so configure the receiver accordingly.
