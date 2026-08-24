# Forward to Traccar

Store the complete Traccar OsmAnd endpoint as `traccar_url`, then use:

```python
p = ctx.telemetry.position
if p is None or ctx.dry_run:
    return

ctx.http.get(
    ctx.secrets["traccar_url"],
    params={
        "id": ctx.vehicle.id,
        "lat": p.latitude,
        "lon": p.longitude,
        "speed": p.speed,
        "bearing": p.heading,
        "timestamp": int(ctx.telemetry.recorded_at.timestamp()),
    },
    timeout=8,
)
```

The Pi sends only to VehiNode. VehiNode remains the durable source of truth and the hook
forwards accepted telemetry to Traccar. A manual retry can duplicate side effects;
configure the receiver accordingly.
