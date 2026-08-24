# Agent diagnostics

Useful commands:

```sh
vehinode-agent status
vehinode-agent doctor
vehinode-agent logs
vehinode-agent config
vehinode-agent gps-info --seconds 20
vehinode-agent obd-info
systemctl status vehinode-agent
```

`status` reports installed credentials and durable queue depth. `doctor` reports the
platform, credential/config directories, GPS discovery and OBD serial candidates.
`logs` reads the latest systemd journal entries.

If cellular service is unavailable, do not delete `queue.sqlite3`. Restore networking
and let the next upload acknowledge queued UUIDs. Repeated upload is safe because both
SQLite and PostgreSQL preserve the stable sample ID.
