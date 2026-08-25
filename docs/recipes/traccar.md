# Forward to Traccar

Store the complete Traccar OsmAnd endpoint as `traccar_url`, then forward every sample the
tracker just delivered:

```python
if ctx.dry_run:
    return

for row in ctx.telemetry_batch:
    p = row.position
    if p is None:
        continue
    ctx.http.get(
        ctx.secrets["traccar_url"],
        params={
            "id": ctx.vehicle.id,
            "lat": p.latitude,
            "lon": p.longitude,
            "speed": p.speed,
            "bearing": p.heading,
            "timestamp": int(row.recorded_at.timestamp()),
        },
        timeout=8,
    )
```

Iterating matters here: a tracker that buffers offline uploads a whole journey at once, and
`ctx.telemetry` alone would forward only its last point. Use `ctx.telemetry` instead when
you only want the current position.

The Pi sends only to VehiNode. VehiNode remains the durable source of truth and the hook
forwards accepted telemetry to Traccar. A manual retry can duplicate side effects;
configure the receiver accordingly.
