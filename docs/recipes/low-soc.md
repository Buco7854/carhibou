# Low-SOC notification

This template logs once when SOC crosses below 20%, then rearms above 23%. It reads
`ctx.telemetry`, the newest sample of the batch, because only the current charge matters:

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

Add an HTTP call using a secret if an external notification is desired. The hysteresis and
persistent state avoid sending one notification per upload.
