# Charging finished notification

Send one message when the pack stops taking charge, using the convention VehiNode
applies everywhere: `battery.power` is negative while the pack absorbs energy. Store
`notify_url` as a secret first.

```python
metrics = ctx.telemetry.metrics
declared = metrics.get("charging.active")
power = metrics.get("battery.power")

# A profile that reports charging directly wins; otherwise derive it from power flow.
if isinstance(declared, bool):
    charging = declared
elif isinstance(power, (int, float)):
    charging = power < 0
else:
    return

was_charging = ctx.state.get("charging", False)
ctx.state["charging"] = charging

if was_charging and not charging:
    soc = metrics.get("battery.soc")
    ctx.log.info("charging finished", soc=soc)
    if not ctx.dry_run:
        ctx.http.post(
            ctx.secrets["notify_url"],
            json={"text": f"{ctx.vehicle.name} finished charging at {soc}%"},
            timeout=8,
        )
```

The transition is what triggers the message, so an unplugged vehicle reporting every few
seconds does not repeat it. Persisting the flag in `ctx.state` is what makes that work
across executions, since each run is a fresh process.

A vehicle that reports neither signal returns early rather than guessing. See
[trusted Python hooks](/user-guide/hooks) for how charging is derived.
