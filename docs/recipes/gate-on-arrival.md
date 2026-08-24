# Gate on arrival

Create secrets `gate_url` and `gate_token`, substitute deliberately non-real demo
coordinates, and create a `telemetry.received` hook:

```python
HOME_LAT = 48.8566
HOME_LON = 2.3522
RADIUS_METERS = 80

position = ctx.telemetry.position
if position is None:
    return

inside = ctx.geo.within_radius(
    position.latitude, position.longitude,
    HOME_LAT, HOME_LON, RADIUS_METERS,
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

This demonstrates radius calculation, transition detection, durable state, secrets and
HTTP without a VehiNode geofence subsystem. Test with dry run first, then verify the
gate API's own authentication, replay protection and safe operating policy.
