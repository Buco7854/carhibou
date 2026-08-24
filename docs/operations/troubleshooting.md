# Troubleshooting

- `/health/live` fails: inspect `docker compose logs app` and container restarts.
- `/health/ready` fails: inspect PostgreSQL health, URL/password and migrations.
- Hooks remain pending: check `docker compose logs worker` and the diagnostics page.
- Hook says lease expired: the worker died; review the failure, then retry manually.
- Tracker is stale: compare its server-owned upload interval, `last_seen`, queue depth,
  `vehinode-agent doctor`, and systemd journal.
- GPS has no position: `gps-info` must show an RMC status `A` or a GGA quality above 0;
  invalid fixes are intentionally ignored.
- C-Zero metric looks wrong: stop treating it operationally, retain a CAN capture and
  report evidence. The shipped profile is experimental.

The admin diagnostics endpoint/page shows version, DB status, worker heartbeat, pending
and failed jobs, hook failures and stale device count without requiring a metrics stack.
