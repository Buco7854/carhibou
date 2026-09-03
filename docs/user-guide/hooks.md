# Trusted Python hooks

A hook is Python that Carhibou runs after it stores new telemetry. Use one to send a
notification, call another service, or remember a small amount of state when something
changes. Hooks run with server privileges, so only administrators can create them.

![The hooks workspace](/screens/hooks.png)

## Quick start

1. Open **Hooks**, create a hook, choose its vehicle and paste the example below.
2. Select **Test with telemetry**. The test uses the vehicle's newest data-carrying
   sample and marks the run as a dry run.
3. Check the execution log, save the hook and enable it.

This hook writes a warning below 20% and rearms only above 23%, avoiding repeated alerts
when the value hovers around the threshold:

```python
# hook-example: low-state-of-charge
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

Add passwords, tokens and private URLs under **Secrets**, then read them with
`ctx.secrets["name"]`; do not paste them into hook source. A dry run executes the hook
normally, but network examples below log what they would send instead of sending it.

## Worked examples

### Charging finished

Store a `notify_url` secret. The hook reacts only to a fresh, resolved charging state and
remembers the previous state, so the initial unknown state is not mistaken for
"not charging."

```python
# hook-example: charging-finished
reading = ctx.telemetry.current.readings.get("charging.active")
if reading is None or not reading.fresh or not isinstance(reading.value, bool):
    return

was_charging = ctx.state.get("charging")
ctx.state["charging"] = reading.value
if was_charging is True and reading.value is False:
    message = f"{ctx.vehicle.name} finished charging"
    if ctx.dry_run:
        ctx.log.info("Would send charging notification", text=message)
    else:
        response = ctx.http.post(
            ctx.secrets["notify_url"],
            json={"text": message},
            timeout=8,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Notification failed with HTTP {response.status_code}")
```

### Gate on arrival

Store `gate_url` and `gate_token`, then replace the demonstration coordinates:

```python
# hook-example: gate-on-arrival
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
was_inside = ctx.state.get("inside_home")
ctx.state["inside_home"] = inside
if was_inside is False and inside:
    if ctx.dry_run:
        ctx.log.info(
            "Would open gate",
            latitude=position.latitude,
            longitude=position.longitude,
        )
    else:
        response = ctx.http.post(
            ctx.secrets["gate_url"],
            headers={"Authorization": f"Bearer {ctx.secrets['gate_token']}"},
            timeout=5,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Gate request failed with HTTP {response.status_code}")
```

The first run records whether the vehicle is inside without opening anything. The
receiving gate still needs its own authentication, replay protection and safe operating
policy.

### Forward recorded positions to Traccar

This example forwards every position included in the hook run, including buffered
positions recorded while the agent was offline:

```python
# hook-example: forward-positions-to-traccar
# A LAN URL with no token is not a secret. If Traccar is reachable from the
# internet, the URL is the only lock: store it as a secret and read
# ctx.secrets["traccar_url"] instead.
TRACCAR_URL = "http://192.168.1.50:5055"
# Must equal the device identifier registered in Traccar; ctx.vehicle.id only
# works if you registered the device under it.
TRACCAR_DEVICE_ID = ctx.vehicle.id

positions = [row for row in ctx.telemetry.triggering if row.key == "position"]
if not positions:
    ctx.log.info("No positions to forward in this run")
    return

for row in positions:
    point = row.value
    state = ctx.telemetry.state_at(row.observed_at)
    soc = state.readings.get("battery.soc")
    battery = soc.value if soc and isinstance(soc.value, (int, float)) else None
    speed_kmh = getattr(point, "speed", None)
    params = {
        "id": TRACCAR_DEVICE_ID,
        "lat": point.latitude,
        "lon": point.longitude,
        "altitude": getattr(point, "altitude", None),
        # Carhibou stores km/h; Traccar's OsmAnd protocol expects knots by default.
        # If you configured OsmAnd for km/h, use speed_kmh directly instead.
        "speed": speed_kmh / 1.852 if isinstance(speed_kmh, (int, float)) else None,
        "bearing": getattr(point, "heading", None),
        "accuracy": getattr(point, "accuracy", None),
        "batt": battery,
        "timestamp": int(row.observed_at.timestamp()),
    }
    # Absent fields stay home: an empty speed= can make older Traccar
    # versions drop the connection without a response.
    params = {key: value for key, value in params.items() if value is not None}
    if ctx.dry_run:
        ctx.log.info("Would forward position to Traccar", **params)
        continue
    response = ctx.http.get(TRACCAR_URL, params=params, timeout=8)
    if response.status_code >= 400:
        raise RuntimeError(f"Traccar request failed with HTTP {response.status_code}")
    ctx.log.info("Forwarded position to Traccar", **params)
```

A manual retry can repeat an external side effect, so configure the receiver to tolerate
duplicates where possible.

## Understanding the data

You do not need this section to use the examples above. It explains which reading a hook
sees when several data sources report independently or an agent uploads buffered data.

### Current state and freshness

`ctx.telemetry.current` is the same resolved vehicle state the dashboard sees. Its
`readings` map contains the latest selected reading for each canonical key. A reading has
`value`, `observed_at`, `source_id`, `source_kind`, `channel`, `method`, and `fresh`.
Current state also provides atomic `position`, `updated_at`, `online`, and agent health.

Missing evidence means unknown, never false. Check that a reading exists, is fresh, and
has the expected type before using it for a decision:

```python
# hook-example: current-state-of-charge
soc = ctx.telemetry.current.readings.get("battery.soc")
if soc is None or not soc.fresh or not isinstance(soc.value, (int, float)):
    return

ctx.log.info("Current state of charge", percent=soc.value, observed_at=soc.observed_at)
```

### What triggered the hook

`ctx.telemetry.triggering` is the tuple of immutable observations that caused this run.
Each item includes `telemetry_id`, `key`, `value`, `observed_at`, source identity,
channel, and method. Atomic position observations use the key `position` and an object
value. A hook run contains at most 10 samples, so a long offline backlog becomes several
bounded runs in recorded order rather than one process large enough to exhaust memory.
The tuple may therefore contain several samples recorded at different times.

Use `triggering` when every newly recorded observation matters, as in the Traccar
example. Use `current` when the decision should be based on the vehicle's resolved state.

### State at a time and bounded history

`ctx.telemetry.state_at(at)` reconstructs the complete known state at a timezone-aware
`datetime`. It uses the same forward-fill rules as the History snapshot table and keeps
each reading's true observation time.

`ctx.telemetry.history(start, end, keys=None, limit=500, offset=0)` returns recorded
observations in an ordered, timezone-aware half-open range. The limit must be 1–1000.
Pass `keys=["position"]` for positions or combine it with metric keys:

```python
# hook-example: historical-context
from datetime import timedelta

end = ctx.event.occurred_at + timedelta(microseconds=1)
start = end - timedelta(hours=1)
previous = ctx.telemetry.state_at(start)
observations = ctx.telemetry.history(
    start,
    end,
    keys=["battery.soc", "charging.active"],
    limit=1000,
)
previous_soc = previous.readings.get("battery.soc")
ctx.log.info(
    "Inspected recent telemetry",
    observations=len(observations),
    previous_soc=previous_soc.value if previous_soc is not None else None,
)
```

## Execution, secrets and dependencies

Hook source is privileged Python, not hostile-code-safe sandboxed code. A fresh child
process provides reliability limits around each run. State is saved only after success,
and runs for one hook are serialized so `ctx.state` read-modify-write behavior is
deterministic. Failures and timeouts stay visible and require an explicit retry because
an external request may already have succeeded.

Secrets are instance-wide, administrator-managed and write-only. Stored values are
encrypted under `CARHIBOU_MASTER_KEY`; logs and tracebacks are redacted against current
values, but hook code can still transmit them. Back up the master key with the database
or the secrets cannot be recovered.

A request that never reaches a server - a refused connection, a timeout, or a port
that answers with something other than HTTP - raises a `RuntimeError` naming the
method and the host and port it tried, and nothing else from the URL. The path,
the query and any credentials are left out because they carry tokens. The
underlying transport error stays chained, so the detail is still in the traceback
below the summary.

The standard library and application dependencies, including `httpx`, are available.
Prefer bounded `ctx.http` calls because they inherit secret redaction. Extra packages
must be pinned into a custom image before the worker starts:

```sh
docker build --build-arg CARHIBOU_HOOK_PACKAGES="paho-mqtt==2.1.0" -t my-carhibou .
```

Set `CARHIBOU_IMAGE=my-carhibou`. A read-only runtime cannot install packages during a
hook execution. **Test with telemetry** always sets `ctx.dry_run`, but dry-run behavior
is advisory: every hook with an external side effect must check it.
