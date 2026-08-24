# Trusted Python hooks

Hooks run on `telemetry.received` or manual test events. Enable a hook only after saving
and testing it. In manual test mode, `ctx.dry_run` is true by default, but VehiNode does
not forcibly suppress HTTP: your code must check the flag when side effects are unsafe.

```python
soc = ctx.telemetry.metrics.get("battery.soc")
if soc is not None and soc < 20:
    ctx.log.warning("Battery is low", soc=soc)
```

Hooks run once by default. Failures and timeouts are recorded; retries are explicit to
avoid silently repeating side effects. Revisions preserve prior source and the editor can
restore a selected revision as a new current revision, leaving the audit trail intact.

::: danger Privileged capability
Anyone who can edit Python hooks has privileged code execution inside the hook worker.
Process limits protect reliability; they are not a hostile-code sandbox.
:::
