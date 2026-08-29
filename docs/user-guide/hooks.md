# Trusted Python hooks

A hook is privileged Python that the worker runs after telemetry is stored. Save and test
it before enabling it. Process limits contain failures for reliability; they are not a
sandbox against an administrator who can edit the source.

![The hooks workspace](/screens/hooks.png)

One accepted upload batch produces one run. The context provides immutable event,
vehicle and agent data, read-only telemetry access, durable JSON `ctx.state`, encrypted
`ctx.secrets`, HTTP and geometry helpers, structured logging, and `ctx.dry_run`.

State is written only after success, and executions for one hook are serialized so
read-modify-write is deterministic. Failures and timeouts remain visible and require an
explicit retry because an external side effect may already have happened. Revisions keep
old source available without rewriting the audit trail.

## Telemetry context

`ctx.telemetry` exposes four read-only views:

- `current` is the same resolved state the dashboard sees. Its `readings` map contains
  reading objects with `value`, `observed_at`, `source_id`, `source_kind`, `channel`,
  `method`, and `fresh`. It also provides atomic `position`, `updated_at`, `online`, and
  the current `agent` health map.
- `triggering` is a tuple of the observations that caused this run. Each item includes
  `telemetry_id`, `key`, `value`, `observed_at`, source identity, channel, and method.
  Atomic position observations use the key `position` and an object value.
- `state_at(at)` reconstructs the complete known vehicle state at a timezone-aware
  `datetime`. It uses the same forward-fill logic as History table mode, retaining each
  reading's true observation time.
- `history(start, end, keys=None, limit=500, offset=0)` returns recorded observations in
  an ordered, timezone-aware half-open range. The limit must be 1–1000. Pass
  `keys=["position"]` for positions or combine it with metric keys.

Missing evidence means unknown, never false. Always distinguish a missing reading from a
reported false boolean, and require `fresh` before using a live value for a decision:

```python
soc = ctx.telemetry.current.readings.get("battery.soc")
if soc is None or not soc.fresh:
    return

ctx.log.info("Current state of charge", percent=soc.value, observed_at=soc.observed_at)
```

Historical reconstruction and queries require timezone-aware timestamps:

```python
from datetime import UTC, datetime, timedelta

end = datetime.now(UTC)
start = end - timedelta(hours=1)
previous = ctx.telemetry.state_at(start)
observations = ctx.telemetry.history(
    start,
    end,
    keys=["battery.soc", "charging.active"],
    limit=1000,
)
```

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

**Test with telemetry** replays the newest accepted telemetry and sets `ctx.dry_run`.
Dry-run behavior is advisory: every side-effecting hook must check it.

## Worked examples

These examples use resolved state and persistent hook state so an event is not repeated
for every reading.

### Low state of charge

```python
soc = ctx.telemetry.current.readings.get("battery.soc")
if soc is None or not soc.fresh or not isinstance(soc.value, (int, float)):
    return

armed = ctx.state.get("armed", True)
if armed and soc.value < 20:
    ctx.log.warning("Battery SOC is low", soc=soc.value, vehicle=ctx.vehicle.name)
    ctx.state["armed"] = False
elif not armed and soc.value > 23:
    ctx.state["armed"] = True
```

The 23% re-arm threshold prevents a hovering value from producing repeated alerts.

### Charging finished

Store a `notify_url` secret. Charging resolution is server-owned: a fresh explicit state
wins, otherwise the backend may derive it from fresh canonical power evidence. The hook
uses the resolved boolean and does not repeat that inference.

```python
reading = ctx.telemetry.current.readings.get("charging.active")
if reading is None or not reading.fresh or not isinstance(reading.value, bool):
    return

was_charging = ctx.state.get("charging")
ctx.state["charging"] = reading.value
if was_charging is True and reading.value is False and not ctx.dry_run:
    ctx.http.post(
        ctx.secrets["notify_url"],
        json={"text": f"{ctx.vehicle.name} finished charging"},
        timeout=8,
    )
```

The initial unknown state is kept distinct from a reported `False` value.

### Gate on arrival

Store `gate_url` and `gate_token`, then replace the demonstration coordinates:

```python
position = ctx.telemetry.current.position
if position is None or not position.fresh:
    return

inside = ctx.geo.within_radius(
    position.latitude,
    position.longitude,
    48.8566,
    2.3522,
    80,
)
was_inside = ctx.state.get("inside_home", False)
if inside and not was_inside and not ctx.dry_run:
    ctx.http.post(
        ctx.secrets["gate_url"],
        headers={"Authorization": f"Bearer {ctx.secrets['gate_token']}"},
        timeout=5,
    )
ctx.state["inside_home"] = inside
```

The receiving gate still needs its own authentication, replay protection and safe
operating policy.

### Forward recorded positions to Traccar

Store the complete OsmAnd endpoint as `traccar_url`. Query the batch's recorded time
range so buffered positions remain individual observations:

```python
from datetime import timedelta

if ctx.dry_run or not ctx.telemetry.triggering:
    return

times = [row.observed_at for row in ctx.telemetry.triggering]
rows = ctx.telemetry.history(
    min(times) - timedelta(microseconds=1),
    max(times) + timedelta(microseconds=1),
    keys=["position"],
    limit=1000,
)
for row in rows:
    point = row.value
    ctx.http.get(
        ctx.secrets["traccar_url"],
        params={
            "id": ctx.vehicle.id,
            "lat": point.latitude,
            "lon": point.longitude,
            "speed": point.speed,
            "bearing": point.heading,
            "timestamp": int(row.observed_at.timestamp()),
        },
        timeout=8,
    )
```

A manual retry can duplicate a side effect, so configure the receiver accordingly.
