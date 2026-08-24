# Agent configuration

The server returns a monotonically versioned configuration during enrollment. The
agent validates a candidate completely before atomically replacing the last-known-good
file. Invalid or older configuration cannot replace a working configuration.

```json
{
  "version": 1,
  "sampling": { "default_seconds": 10 },
  "upload": { "default_seconds": 30 },
  "vehicle_profile": "citroen-c-zero-v1"
}
```

Sampling and uploading are separate: at the example settings, three durable SQLite
samples are normally sent in one request. The queue remains authoritative through
network loss and deletes only sample IDs acknowledged by the server.

The service authenticates and checks for server configuration every five minutes.
Same-version responses cause no file write. A syntactically invalid value, rollback, or
reference to an uninstalled profile is rejected before replacing the working file.

Inspect the accepted configuration with `vehinode-agent config`. Hardware serial paths
can be overridden on `vehinode-agent run` with `--gps-device` and `--obd-device`; use
stable `/dev/serial/by-id/...` paths whenever possible.
