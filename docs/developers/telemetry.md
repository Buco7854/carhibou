# Telemetry ingestion

`POST /api/v1/device/telemetry/batch` accepts up to 500 samples. Each carries a stable
UUID, boot-local sequence, UTC timestamp, optional position, canonical metric map and
device-health map. PostgreSQL uniquely constrains sample UUIDs; a retry after a lost
response reports the row as duplicate without changing history or rerunning hooks.

Position and common query dimensions are relational columns. Variable canonical
metrics remain JSONB. The newest recorded sample updates `vehicle_state`, making live
dashboards cheap. Older delayed samples are stored in history but cannot rewind current
state.

History requests have a bounded range and result size. The service reduces dense data
server-side before returning route/chart points. PostgreSQL remains the only time-series
store at the intended 1–100 vehicle scale.

## Live browser state

Authenticated browsers subscribe to `GET /api/v1/events/stream`, a same-origin
Server-Sent Events stream. The server sends a versioned `vehicle.states` snapshot when
owned current state changes and a comment heartbeat while idle. The dashboard updates
its state immediately and refreshes route history only for a newly received sample;
there is no fixed browser polling interval.

The stream uses the opaque browser session cookie, revalidates that session while it is
open, and emits `session.expired` before closing a revoked or expired connection. Device
credentials cannot open it. Snapshots come from PostgreSQL rather than process-local
memory, so multiple app processes remain consistent. The EventSource client reconnects
automatically after temporary network or server failures.
