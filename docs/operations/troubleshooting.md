# Troubleshooting

Start by checking service state and recent logs:

```bash
docker compose ps
docker compose logs --tail=200 app worker postgres
```

## The web interface does not open

Run `curl -v http://localhost:8000/health/live` on the Docker host. If it fails, inspect
`docker compose logs app` for configuration validation, migration or port-binding
errors. If it works locally but not through your hostname, inspect the TLS reverse proxy
and firewall rather than changing VehiNode credentials.

## Readiness fails

`/health/ready` checks PostgreSQL. Confirm that `postgres` is healthy in
`docker compose ps`, then inspect its logs. A password changed in `.env` does not alter
the password already stored inside an existing PostgreSQL volume; restore the matching
value or follow a deliberate database password-rotation procedure.

## Login loops behind HTTPS

Confirm that `VEHINODE_PUBLIC_URL` exactly matches the browser origin and that
`VEHINODE_SESSION_COOKIE_SECURE=true`. The reverse proxy must forward HTTPS requests to
the app without placing the API on a different browser origin.

## Hooks remain pending or fail

Check `docker compose logs worker` and the diagnostics page. A lease-expired execution
usually means a worker stopped during the job. Review the execution record before using
manual retry because a hook may already have produced an external side effect.

## An agent is stale

Compare the agent's configured upload interval, `last_seen` and queue depth. On the
Pi, run `vehinode-agent doctor` and inspect the systemd journal. A parked vehicle with a
slow reporting interval should not be treated the same as a disconnected agent.

## GPS or vehicle data looks wrong

- `gps-info` must show an RMC status `A` or a GGA quality above 0. Invalid fixes are
  intentionally ignored.
- If a C-Zero metric looks wrong, stop treating it operationally, retain a CAN capture,
  and report the evidence. The shipped profile remains experimental.

The admin diagnostics endpoint/page shows version, DB status, worker heartbeat, pending
and failed jobs, hook failures and stale device count without requiring a metrics stack.
