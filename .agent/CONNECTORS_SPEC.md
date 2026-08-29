# External data connectors: MQTT / TeslaMate

## Naming decision (applies repo-wide after the connector feature lands)

Three names, each consistent across database, code, routes, UI, and docs, with no
backward-compatibility aliases:

- "Data sources": the umbrella page listing both kinds. Route `/data-sources`, view
  `DataSourcesView`, docs page `user-guide/data-sources.md`, nav label "Data sources"
  (fr "Sources de données").
- "Agent": the enrolled push entity, replacing every use of "device" for it: table
  `devices` → `agents`, model `Device` → `Agent`, human routes `/devices` → `/agents`,
  device-facing prefix `/device/*` → `/agent/*`, auth scheme `Authorization: Device` →
  `Authorization: Agent`, `telemetry.device_id` → `agent_id`, the sample `device`
  field, `device_data` column and `device:` history-key prefix → `agent`,
  `device-health` widget → `agent-health`, i18n namespace `devices` → `agents`.
- "Connector": the server-hosted entity, exactly as this spec already names it.

The connector feature is implemented first under current names; the rename is a
separate coordinated pass immediately after, run against this section as contract.
This section is recorded now so no new code invents competing names.

## Goal

Carhibou currently receives telemetry only from enrolled agents that push to the agent
API. Connectors are the second kind of data source: server-hosted subsystems that
receive or fetch data from an external system and feed it into the same telemetry
pipeline. The first transport is MQTT subscription, and the first bundled source
mapping is TeslaMate. The design must stay generic: TeslaMate is one mapping over a
generic MQTT connector, not a special case in the pipeline.

## TeslaMate publishing facts (verified against source)

- Topics: `teslamate/[namespace/]cars/$car_id/<key>`, about 78 keys per car.
- All keys except `healthy` are published with `retain=true` at QoS 1, on change only.
  Subscribing therefore yields an immediate full snapshot, then deltas.
- Values are strings: booleans as `"true"`/`"false"`, datetimes ISO8601, numbers as
  plain decimal strings, `location` and `active_route` as JSON objects, and the string
  `"nil"` appears for some route fields.
- Deprecated duplicate topics exist (`latitude`, `longitude`, `active_route_destination`,
  `active_route_latitude`, `active_route_longitude`) and must be ignored in favor of the
  JSON blobs.
- The broker is the user's own (for example Home Assistant's Mosquitto): host, port
  (default 1883), optional username/password, optional TLS with an
  accept-invalid-certs escape hatch, optional namespace.

## Data model

New table `connectors`:

- `id`, `vehicle_id` (FK, one vehicle per connector), `name`
- `kind` (string, catalog id; initially only `teslamate.mqtt`)
- `enabled` (bool)
- `config` (JSON: host, port, tls, tls_accept_invalid_certs, username, namespace,
  car_id, sample_seconds)
- `password` stored server-side (outbound credential, so it cannot be hashed); it is
  write-only in the human API exactly like hook secrets: accepted on create/update,
  never echoed back, masked marker in responses
- `config_version` (int, bumped on every config change; the runtime uses it to know
  when to restart a session)
- runtime status columns, written by the worker and read-only in the API:
  `status` (`disabled` | `connecting` | `connected` | `error`), `last_connected_at`,
  `last_message_at`, `last_sample_at`, `last_error` (string, empty when healthy)
- `created_at`, `updated_at`

Each connector owns a shadow `Agent` row so telemetry keeps its FK integrity and the
existing state/history/hook/online machinery works unchanged:

- `implementation_id` is `connector.teslamate.mqtt` (prefix `connector.` is reserved:
  manifests may not use it, enrollment tokens may not name it, and `/agent/enroll`
  rejects it)
- `protocol_version` 2, `agent_version` = server APP_VERSION, unusable random
  credential, cadence fields mirror `sample_seconds`
- credential rotation and enrollment-style actions on a connector-backed agent return
  400; revoking is expressed by disabling the connector; deleting the connector deletes
  its shadow agent (and thereby follows existing agent-deletion semantics)
- agent listings exclude connector-backed agents unless explicitly included; the
  human API exposes connectors as first-class resources instead

Schema changes follow the project convention: extend the squashed initial migration.

## Source mappings

A mapping turns broker messages into telemetry samples. Mappings are data, bundled in
the backend (`backend/app/connectors/mappings/teslamate.py` or equivalent), and every
rule is unit-tested. The TeslaMate mapping:

- Canonical targets (existing key conventions): `battery_level` → `battery.soc`,
  `power` → `battery.power` (kW; verify sign convention matches ours: negative while
  charging), `odometer` → `vehicle.odometer`, `charger_power` → `charging.power`,
  `est_battery_range_km` → `vehicle.range`, `charge_limit_soc` → passthrough,
  `tpms_pressure_{fl,fr,rl,rr}` → `tyre.<corner>_pressure`,
  `tpms_soft_warning_*` → the existing tyre-warning keys if present, else passthrough,
  `state`/`charging_state` → `vehicle.state` and a boolean `charging` consistent with
  what the bundled agent reports. Cross-check every canonical key against
  `frontend/src/vehicleDisplay.ts` before finalizing; do not invent near-duplicates.
- Position targets: `location` JSON → latitude/longitude, `elevation` → altitude,
  `heading` → heading, `speed` → position speed (TeslaMate publishes km/h; match the
  unit the Go agent uses for gps speed, converting if needed).
- Everything else passes through under the `teslamate.` prefix with its topic key,
  for example `teslamate.inside_temp`, `teslamate.sentry_mode`. JSON-object values are
  flattened one level (`teslamate.active_route.minutes_to_arrival`); deeper structure
  is dropped. The deprecated topics listed above are ignored.
- Value coercion is per-value and fail-open: numeric strings become floats, `true`/
  `false` become booleans, `"nil"`/empty becomes absent, anything else stays a string.
  A value that fails coercion drops that key for that sample only and increments an
  error note in connector status; it never rejects a sample or batch, and never
  changes the connector to an error state.

Metric keys already flow through the whole pipeline as opaque strings (ingestion
validation, JSON storage, history key discovery, dashboard free-text metric fields,
frontend label fallbacks), so novel and disappearing keys need no schema work. A
metric that stops arriving simply stops updating, exactly like an agent metric.

## Runtime

- The connector runtime lives in the existing worker process (`backend/app/worker.py`)
  as a supervisor thread beside the job loop: one MQTT session per enabled connector,
  reconnect with capped exponential backoff, per-connector isolation (one connector's
  failure never affects others or job processing). Worker shutdown stops sessions
  cleanly. The supervisor re-reads the connectors table on a short interval and
  applies create/delete/enable/disable/config_version changes without a worker restart.
- Client library: choose a maintained Python MQTT client (paho-mqtt v2 is the default
  choice); pin it in pyproject following the repo's dependency style.
- Sampling: messages accumulate into a per-connector buffer; every `sample_seconds`
  (default 10, bounds 1 to 3600) with at least one change, the buffer becomes one
  telemetry sample (UUID id, fresh boot_id per session, sequence increasing,
  `recorded_at` = window close) ingested through the existing `ingest_batch` service
  in-process, which also fires hooks and updates live state. The retained snapshot on
  connect produces one initial full sample.
- Status writes are throttled (no more than one status row update per few seconds)
  so a chatty broker cannot melt the database.

## Human API and access

Session realm, mirroring agent management:

- `GET /connector-kinds` (any authenticated user): catalog, initially one entry
  `{id: "teslamate.mqtt", name: "TeslaMate (MQTT)", description, docs_url}` shaped for
  future kinds.
- `GET /connectors`: connectors for vehicles the user may view, each with runtime
  status; config echoed without password (masked marker only).
- `POST /vehicles/{id}/connectors` (operator): `{kind, name, config..., password?}`.
- `PUT /connectors/{id}` (operator): name, enabled, config, optional new password;
  bumps `config_version`.
- `DELETE /connectors/{id}` (operator): removes connector and shadow agent.
- Validation fails closed: unknown kind, unknown config keys, invalid host/port.

## Frontend

- The Data sources page gains a distinct connector section listing connectors:
  name, vehicle, kind, status chip (connected / connecting / error / disabled),
  last message time, and last error text when in error. Rows offer edit, enable or
  disable, and delete for operators, following existing action idiom.
- An "Add data source" flow (parallel to "Add agent"): choose the kind from the
  catalog, choose the vehicle (operable vehicles only), then the TeslaMate form:
  host, port, TLS toggle plus accept-invalid-certs sub-toggle, username, password
  (write-only field with masked placeholder on edit), namespace (optional), car id
  (default 1), sample interval. Hint text explains pointing it at the same broker
  TeslaMate publishes to (for example Home Assistant's Mosquitto) and that data
  appears under existing metric names plus the `teslamate.` prefix.
- Connector-backed shadow agents do not appear in the agents list.
- Both locales complete; tests cover the section rendering with each status, the
  create flow payload, password write-only behavior on edit, and that dashboards
  and history continue to work with `teslamate.`-prefixed keys (existing fallback
  rendering).

## Verification

- Mapping tests: a fixture covering all 78 TeslaMate topics asserts the exact
  produced sample (canonical keys, position fields, passthrough keys, flattening,
  deprecated-topic ignoring, coercion edge cases including "nil", type changes, and
  unknown new topics).
- Runtime tests: fake client injected into the session (no real broker in CI):
  snapshot-then-delta batching, sample_seconds windowing, backoff/reconnect status
  transitions, per-value failure isolation, config_version restart, disable/delete
  teardown.
- API tests: access matrix (viewer/operator/stranger/admin), password write-only,
  fail-closed validation, reserved implementation prefix rejected at /agent/enroll
  and in manifests.
- End-to-end: injected messages → sample → live state, history keys, and hook firing.
- Frontend tests as above. Full repo gate must pass.

## Documentation

- User guide `docs/user-guide/data-sources.md`: a "Data sources" section with TeslaMate
  setup against Home Assistant's Mosquitto.
- `docs/developers/architecture.md`: connector subsystem, mapping model, and the
  reserved `connector.` implementation prefix. Existing page structure, no new pages,
  no em dashes, never "self-hosted".
