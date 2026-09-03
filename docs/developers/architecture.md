# Architecture

Carhibou is a modular monolith for roughly 1–100 vehicles. One Python codebase provides
the FastAPI application and a PostgreSQL-backed worker; both share one schema. A Vue 3
SPA is compiled by Vite and served as static production files. PostgreSQL is the only
stateful server dependency and also holds the durable job queue.

The vehicle-side agent is a separate CGO-free Go executable with serial hardware, HTTPS
and an embedded SQLite outbox. Release builds target Linux ARMv6, ARMv7, ARM64 and AMD64
without requiring a language runtime on the vehicle host.

Domain modules own their models, schemas, routes and services. Routes validate and
authorize; services own transactions and domain behavior. Alembic is the only production
schema creation mechanism.

## API boundary

The generated OpenAPI document at `/api/openapi.json` is authoritative; interactive
documentation is at `/api/docs`. Product routes live under `/api/v1`. Validation errors
use FastAPI's structured `detail`, list endpoints impose explicit bounds, and oversized
bodies are rejected before parsing. Responses carry `X-Request-ID`, accepting a valid
caller-supplied value for trace correlation.

Browser calls use a human session cookie and send the readable CSRF cookie as
`X-CSRF-Token` for mutations. Agents instead use `Authorization: Agent CREDENTIAL`,
accepted only by `/api/v1/agent/*`.

## Agent protocol

Agent implementation identity and wire compatibility are separate facts:

- `implementation_id` names an implementation such as `carhibou.go` or `custom`.
- `agent_version` is that implementation's own release version and is informational.
- `protocol_version` is the integer Carhibou uses to accept or reject the wire contract.

`agent_version` is never compared with the Carhibou server version. Compatibility is
computed from `protocol_version`; the server currently accepts protocol version `2`.

Enrollment tokens are single-use and bound to one `implementation_id`. A request naming a
different implementation or an unsupported protocol is rejected before the token is
consumed. Successful enrollment persists the implementation id, agent version and protocol
version, then returns an agent credential and complete configuration. The credential remains
restricted to agent routes. The generated OpenAPI document is the field-level reference for
enrollment, configuration and telemetry payloads.

A maintained implementation normally consists of one top-level directory containing
`agent.toml`. Manifest schema version `1` declares the stable id, display name, supported
hardware summary, integer `protocol_version`, setup kind (`command` or `guided`), optional
documentation URL and ordered setup steps. A step is `command`, `value`, `link` or `manual`.
Static step strings may substitute `{server}`, `{token}` and `{protocol_version}`. Values
inserted into command steps are shell-quoted.

The parser fails closed on missing required fields, unknown keys, unknown schema versions,
duplicate implementation ids and malformed steps or templates. The production image
collects manifests independently of Python packaging, so an implementation may use any
language and distribution method. Backend code is reserved for setup that cannot be
expressed as static manifest steps, as with the bundled release-specific installer command.

## Connector subsystem

Connectors are worker-hosted telemetry producers for external systems. The human API owns
configuration and access checks; the worker supervisor periodically reconciles enabled
connectors and runs one isolated session per connector. A configuration version change
restarts only that session. MQTT connections use capped exponential reconnect backoff, and
worker shutdown closes every session cleanly.

Each connector owns a shadow agent with the same id. This preserves telemetry foreign keys
and reuses the existing atomic ingest path for current state, history, triggers and hook jobs.
Shadow agents have unusable credentials and are hidden from agent listings. The
`connector.` implementation prefix is reserved for this purpose: manifests, enrollment
tokens and agent enrollment requests cannot claim it. Connector settings, enablement and
deletion are available only through connector routes.

Source mappings are typed profiles at the transport boundary. A shared mapping engine
receives a source key and value and emits canonical metrics, position fields or namespaced
passthrough metrics. Profile validation fails closed on unknown fields, duplicate matches,
invalid targets and incompatible transforms. Runtime coercion is fail-open per value, so a
bad value is omitted while the session continues processing other keys.

Connectors reference a mapping profile separately from their connection settings. Editing
a referenced profile or selecting another one increments the connector configuration
version and restarts only that session. Agents reference CAN profiles instead, and receive
their projected decoder definition through the existing versioned configuration. Profile
types cannot be exchanged between those two source kinds.

The bundled `teslamate-mqtt-v1` profile translates stable TeslaMate keys and keeps other
values below `teslamate.`. It ignores deprecated duplicate position and route topics in
favor of the JSON topics. Scalar strings are coerced independently, JSON objects are
flattened by one level, and mapping notes do not change a healthy MQTT session to an error
state.

TeslaMate publishes retained QoS 1 values on change, so the first subscription delivers a
snapshot followed by deltas. A session accumulates those changes into one telemetry sample
per configured window. It retains the last complete position locally so a metric-only delta
does not clear location. Samples enter `ingest_batch` in-process with a fresh boot id for the
session and an increasing sequence. Runtime status writes are throttled independently from
telemetry ingestion.

## Authentication and access

`AuthenticationIdentity` links a provider identity, local password or OIDC, to `User`.
Vehicles belong to the instance; per-vehicle grants refer to users and are resolved only
through the access module. Dashboards remain personal resources.

Local passwords use Argon2id. Browser tokens are opaque and only a keyed hash is stored.
Sessions expire, can be revoked, and are invalidated by password change or suspension.
Cookies are HttpOnly, SameSite=Lax and Secure in production; mutations use a
session-bound double-submit CSRF token.

Local registration is a one-time bootstrap boundary: it succeeds only with no users and
always creates the first administrator. Startup can perform the same idempotent action
from `CARHIBOU_BOOTSTRAP_ADMIN_*`, but cannot create another user. Later accounts come
from an administrator or OIDC auto-provisioning and copy the default-access template.
OIDC resolves a linked provider subject first, then may link by verified email. Its admin
group is re-evaluated on every login with the same last-active-admin guard used by local
management.

The last active administrator cannot be demoted, suspended or deleted, and an
administrator cannot remove their own access. Agent credentials remain an independent
hash and dependency: an agent credential cannot authorize human routes, and a browser
session cannot authorize agent routes.

## Telemetry transaction

`POST /api/v1/agent/telemetry/batch` accepts at most 500 protocol-v2 samples, each with
a stable UUID, boot-local sequence, UTC timestamp, optional atomic position observation,
independent metric observations and agent health. Source identity comes from the agent
credential; channel and observation time travel with each value. A unique sample UUID
makes retries idempotent without changing history or rerunning hooks.

One transaction stores immutable observations, advances newer per-source candidates,
resolves the vehicle's live readings, creates generic triggers of at most 10 samples and
queues matching hook jobs. The Go agent sends catch-up data in independently acknowledged
requests of at most 200 samples; the smaller hook bound leaves time for a hook that makes
one external request per sample. A delayed observation can update one metric
without overwriting a newer unrelated one. Candidate freshness follows the source cadence recorded with the observation;
safety-sensitive values expire to unknown while persistent values remain visibly stale.
PostgreSQL is the time-series store at the intended scale.

The bounded history endpoint downsamples route and chart points. Snapshot table mode
reconstructs the complete known state at each requested bucket boundary, forward-fills
each reading with its true observation time and collapses unchanged quiet spans. Raw
observations remain available as a separate paginated provenance view.

The segments endpoint derives drives and charges on read from recorded observations, so it does
not depend on history downsampling and stores no session records. Explicit lifecycle edges
take precedence: recorded in-use state keeps traffic stops inside one drive and closes it
on a parked reading, while explicit charging state (or charging power when no state exists)
keeps a charge continuous across the parked sampling cadence until an inactive reading.
Vehicles without lifecycle signals fall back to joining speed and position evidence less
than 180 seconds apart. Segments shorter than 60 seconds are discarded and queries are
capped at 92 days.
Distance prefers odometer change and falls back to GPS haversine distance. Charge energy
prefers the source's accumulated energy and falls back to trapezoidal power integration.
Missing source metrics omit only their optional response fields.

Authenticated browsers receive current-state snapshots from
`GET /api/v1/events/stream`. This same-origin SSE stream reads PostgreSQL rather than
process memory, sends heartbeats while idle, revalidates its session, and emits
`session.expired` before closing a revoked session. New telemetry updates live state
immediately; route history refreshes only for a new sample, without fixed browser polling.

## Trusted hook runtime

Ingestion queues one execution per matching hook per bounded trigger, then returns. The
worker claims jobs with `FOR UPDATE SKIP LOCKED` and starts a fresh child process. Wall
and CPU time, memory, file output, HTTP response bodies, error text and result previews
are bounded for reliability; privileged Python is not treated as hostile-code-safe.
Complete structured logs are streamed through a bounded temporary archive, persisted in
batches outside the child result and exposed through a paginated admin endpoint.

SDK v3 exposes immutable `ctx.event`, resolved `ctx.telemetry.current`, the observations
that caused the run in `ctx.telemetry.triggering`, state-at-time reconstruction and
bounded raw history queries. Vehicle and agent projections, durable JSON state,
encrypted secrets, HTTP and geometry helpers, structured logging, and `ctx.dry_run`
remain available. ORM entities never cross the boundary. State serializes only on
success and executions for one hook are serialized.

Failures, timeouts and recovered crashes are visible but not automatically retried,
because arbitrary external side effects may not be idempotent. A manual dry run remains
advisory: hook code must suppress unsafe requests itself.

The event envelope is versioned and supports future schedule, presence, trip, charging
or geofence producers. New producers should create their trigger and jobs inside their
own state transaction rather than adding a second queueing system.

## Verification boundary

Completion requires migrations, Python lint/types/tests, Go format/vet/tests and
cross-builds, frontend tests/build, documentation build, PostgreSQL integration, browser
E2E and container smoke tests. Software and fixture completion can coexist with pending
physical validation; only the [hardware ledger](/agent/diagnostics#hardware-validation-ledger)
may claim physical evidence.
