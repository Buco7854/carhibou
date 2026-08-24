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
