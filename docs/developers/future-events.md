# Future events

Hooks consume a stable envelope with ID, type, version, occurrence time, optional
vehicle/device IDs and payload. V1 producers emit `telemetry.received` and
`manual.test`. Hook execution code does not assume a trigger always originated from a
telemetry row, although the current context builder requires telemetry for those two
implemented producers.

Future producers—schedule, device presence, trip, charging, geofence or custom events—
should create the same durable trigger and jobs within their own state transaction.
They are intentionally not implemented until a concrete product need exists.
