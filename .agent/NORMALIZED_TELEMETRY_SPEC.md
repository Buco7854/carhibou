# Normalized telemetry and live-state contract

Status: implementation contract

Compatibility policy: protocol v2 and the normalized state model ship as a
brand-new application. There is no upgrade path and no transitional
migration: the schema lives in a single initial migration that already
contains the v2 model, existing databases are recreated rather than
migrated, and no v1 wire aliases, legacy state response fields, telemetry
backfill, or queued-sample conversion exist anywhere. The agent may reset
its telemetry outbox freely.

## Semantics

- A telemetry sample is a transport envelope, not a complete vehicle snapshot.
- Every metric is an independent observation and may arrive alone.
- History stores accepted samples without carrying unrelated values forward.
- The authenticated agent or connector is the source. A channel (`can`, `obd`,
  `gnss`, `mqtt`, or `derived`) describes how that source obtained a value.
- Profiles translate raw source data into canonical observations. They never
  invent a canonical mapping whose physical meaning or unit is uncertain.
- Unknown or source-specific values remain namespaced and are still available
  to history, hooks, and generic dashboard shapes.

## Observation wire model

Backward compatibility is not a constraint. The telemetry wire format uses
first-class observations rather than parallel value and metadata maps:

```json
{
  "observations": [
    {
      "key": "vehicle.speed",
      "value": 42.1,
      "observed_at": "2026-08-28T12:00:05Z",
      "channel": "can",
      "method": "direct"
    }
  ]
}
```

The source identity is inferred from authentication and is never accepted from
the payload. `(key, channel)` is unique within one sample. An explicit null
retracts that source/channel candidate; omission means no new observation.

Position is one atomic observation. Its metadata applies to latitude,
longitude, altitude, speed, heading, and accuracy together. GNSS speed becomes
a candidate for the canonical `vehicle.speed` reading without splitting the
position fix.

## Canonical metric registry

Every canonical metric definition owns:

- key, value type, and canonical unit;
- physical/sign semantics and validation range;
- kind: measurement, state, counter, or event;
- freshness and stale-value behavior;
- candidate resolution policy;
- history aggregation behavior where applicable.

Canonical keys cover only semantics Carhibou can prove. Extension keys remain
namespaced. Registry validation is per value and fail-open for the containing
sample: one invalid observation is rejected without discarding unrelated data.

Initial cross-source rules:

- `vehicle.speed`: choose among fresh candidates; direct CAN/OBD speed wins over
  GNSS speed when both are fresh, otherwise use the fresh candidate.
- `charging.active`: a fresh explicit boolean is authoritative in both
  directions. Otherwise it may be derived from fresh canonical power evidence
  using the shared charging floor. No evidence means unknown, not false.
- Other canonical metrics: choose a valid fresh direct candidate, then a valid
  fresh derived candidate, with observation time as the final tie-breaker.
- Persistent state/counter readings may remain last-known but must be marked
  stale. Safety-sensitive live states such as charging become unknown when
  their evidence expires.

## Persistence and resolution

History remains immutable. Candidate state retains the latest observation for
each `(vehicle, source, channel, metric)` with value, observation time, method,
and telemetry id. Position candidates are retained atomically.

The existing vehicle live state remains the dashboard projection. It contains
flat resolved values plus selected provenance metadata. Candidate state is an
internal input to that projection, not another user-facing state model.

Ingestion holds the existing per-vehicle lock and atomically:

1. appends non-duplicate history samples;
2. applies newer observations to source candidates;
3. resolves affected canonical readings and position;
4. updates the existing vehicle live state;
5. enqueues hooks and commits.

Delayed samples update a candidate only when their observation time is newer
for that exact source/channel/metric. A newer unrelated position must not block
an older-but-previously-unseen battery observation. Candidate expiration is
evaluated when live state is read as well as when related observations arrive,
so time passing alone can make a safety-sensitive value unknown.

## Public API

The live-state API exposes one resolved reading object rather than parallel
value and metadata maps:

```json
{
  "readings": {
    "vehicle.speed": {
      "value": 42.1,
      "observed_at": "2026-08-28T12:00:05Z",
      "source_id": "agent-1",
      "source_kind": "agent",
      "channel": "can",
      "method": "direct",
      "fresh": true
    }
  }
}
```

Resolved position likewise carries its selected provenance as one atomic
object. Widgets never resolve competing sources. Backend state resolution is
the only authority for live fallback selection. History continues to expose
recorded observations and uses the same canonical definitions for derived
analysis. The database may retain compact value/metadata JSON internally; its
storage shape does not weaken the observation contract.

## Required invariants

- History insertion, candidate updates, live-state resolution, trigger
  creation, and job enqueueing remain atomic.
- Source identity comes only from the authenticated ingestion realm.
- Invalid or type-changing extension values cannot reject unrelated metrics or
  make a vehicle inaccessible.
- Candidate provenance distinguishes source identity from acquisition channel:
  for example `source = agent-1, channel = gnss`.
- Multiple agents and connectors may independently contribute different or
  overlapping metrics to one vehicle.

## History API v2 requirements

History serves the same immutable observations in two read modes:

- Observations mode: the recorded observations as received (sparse, v2
  shapes) — the existing raw list, charts, and route views.
- Table mode: a computed, resolution-bucketed table (second/minute/hour-class
  steps) ordered newest to oldest. Each row recreates the snapshot effect:
  "at this time the car was in this state" — the complete known vehicle
  state, every reported metric's last-known value forward-filled as of the
  bucket's end, never only the partial values that happened to arrive in
  that bucket. Every carried cell keeps its true observation time so a
  forward-filled value is visibly old rather than freshly measured. Long
  quiet spans must stay cheap: identical consecutive rows may be collapsed or
  paginated server-side rather than materialized row by row.

The exact response schema is designed by the backend implementation and
documented in this file; the frontend follows it in a second pass.

## Cadence-aware freshness

Registry freshness windows are floors and defaults, not the whole truth.
Every displayed value is at least one delivery interval old, so "fresh" must
mean "within this source's normal cadence", never "recent by wall-clock
taste".

- Each upload declares the source's current delivery promise: either
  `reporting_interval` — the maximum expected gap in seconds until that
  source's next delivery, covering sampling cadence, parked cadence, and
  upload batching, whichever dominates — or `event_driven: true`, meaning
  silence signals "unchanged" for as long as the source stays connected.
- A candidate stores the promise that was in force when its observation
  arrived. A sampled candidate is fresh while
  `now − observed_at ≤ max(registry window, K × declared interval)`,
  with K a shared registry constant (default 3). A value observed under the
  driving cadence expires on the driving clock even if the source later drops
  to a parked cadence: a value is judged by the promise it was delivered
  under.
- An event-driven candidate stays fresh while its source remains in contact
  within its own liveness window; when contact is lost it expires from the
  last contact time using the registry window. Retained metrics degrade to
  stale as usual; non-retained ones go unknown.
- Explicit retraction beats timeout: when a producer knows a channel died
  (OBD unplugged, adapter errored, provider stopped, clean shutdown), it sends
  the null retraction from the observation contract instead of letting values
  age out. Timeout expiry is the fallback for sources that vanish without
  saying so.
- A quiet channel is not a dead one. A vehicle whose bus stops broadcasting
  while its adapter still answers is asleep, not gone: the producer sends
  nothing, reports the silence in its source state, and lets the values age
  under the rules above. Retraction is reserved for hardware that is no longer
  there, because retracting on silence makes retained metrics vanish every
  night the vehicle sleeps.
- Sources that declare nothing keep plain registry-window behavior. The
  server tracks last contact per source; widgets still only ever see the
  resolved `fresh` flag.

## Hook context v2 requirements

A hook is no longer limited to the batch that triggered it. The hook runtime
exposes, read-only and efficiently:

- the triggering observations (what actually arrived, with provenance);
- the current resolved vehicle state (the same readings the dashboard sees);
- the full known vehicle state at any requested time — the same
  state-at-time reconstruction that powers the history table mode, shared
  implementation, same forward-fill and provenance semantics;
- bounded queries over recorded history observations (any data, not only
  the triggering batch).

The exact hook context API is designed by the backend implementation and
documented here; the frontend's default hook template follows in the
integration pass.

## Implemented v2 read surface (as landed)

History endpoints, all vehicle-scoped:

- `GET …/history` and `GET …/history/entries`: unchanged raw experiences
  (points/entries with flat metrics). They serve recorded observations, not
  resolved readings, so their consumers may legitimately look at raw
  position speed.
- `GET …/history/observations`: paginated samples as received. Each sample:
  `id`, `sequence`, `recorded_at`, `received_at`, `source_id`,
  `source_kind`, `reporting_interval`, `event_driven`, atomic `position`
  observation, `observations` list (`key`, `value`, `observed_at`,
  `source_id`, `source_kind`, `channel`, `method`), `agent` map.
- `GET …/history/table?step_seconds=…`: the snapshot table. Supported steps
  are exactly {1, 5, 10, 30, 60, 300, 900, 3600, 21600, 86400}; anything
  else is a 400, never rounded. Response: `step_seconds`, `total`, `limit`,
  `offset`, and `rows` of `{bucket_start, bucket_end, collapsed_buckets,
  readings: key → reading, position, agent}`, newest to oldest; identical
  consecutive buckets collapse into one row carrying `collapsed_buckets`.

Hook context (implemented in `backend/app/hooks/context.py`; the v1
`ctx.telemetry.metrics` and `ctx.telemetry_batch` no longer exist):

- `ctx.telemetry.current` — resolved readings and position, as the dashboard
  sees them;
- `ctx.telemetry.triggering` — the observations that fired the hook, with
  provenance;
- `ctx.telemetry.state_at(t)` — full known state at a timezone-aware time,
  shared reconstruction with the history table;
- `ctx.telemetry.history(...)` — bounded raw queries (limit 1..1000).

Known follow-ups: `GET …/history/observations` is implemented but not yet
consumed by the frontend; `formatDuration` in the frontend cadence display
mis-pluralizes units (new `formatSpan`/`formatAge` are correct).
