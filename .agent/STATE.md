# Current project state

Updated: 2026-09-04

## Works

- The modular monolith implements local session authentication, vehicle ownership,
  one-time agent enrollment, separate agent credentials, idempotent telemetry,
  current state, bounded history, dashboards, diagnostics and explicit migrations.
  Local registration can create only the first administrator; an administrator adds
  everyone afterwards from Settings, and may suspend, promote or delete an account. The
  last active administrator cannot be demoted, suspended or deleted, and nobody can
  remove their own access, so an instance always keeps a way back in. That account can instead
  be bootstrapped idempotently from environment variables; later registration is always
  rejected and the identity boundary remains ready for a future OIDC provider.
- The Tailwind Vue SPA is a sidebar-only instrument workspace: navigation, account,
  theme and language live in one rail and there is no second title bar repeating the
  page heading. A versioned premade Overview, multiple owner dashboards, responsive
  single-column mobile widgets, route/history charts, tracker administration, hooks and
  settings are functional. The searchable garage uses dimensionally stable photo cards
  and leaves optional vehicle facts blank. Self-hosted IBM Plex typography, an original
  node-route mark, configurable OpenFreeMap vector cartography, optional owner-scoped
  vehicle photos with a plain missing-image placeholder, a validated categorical chart
  palette checked against both surfaces, extensible English/French catalogs,
  browser-language detection, app-owned accessible dropdowns, modal creation flows and
  persistent Light, Dark and Auto themes work across the application. Maps may follow
  the interface with separately selected provider styles for light and dark, or keep one
  provider style regardless of interface and browser theme; Liberty and Dark are the
  defaults. Map controls (expand, zoom) are the app's own buttons, translated and sized
  as targets; the speed trail is painted with a data-relative quantile ramp in one hue
  that follows the basemap's tone rather than the interface theme, with a legend printing
  the drive's own band edges and a hover/tap readout of speed and time per segment; the
  card context (A-to-B readout, pick hint, heading) lives inside the map frame so it
  travels with the map when expanded. OpenFreeMap's automatic attribution is kept intact.
  Primary actions carry the accent blue rather than near-black ink, in both themes.
  Surfaces carry no decorative section kickers, self-describing subtitles, duplicated
  KPI strips or status theater; page copy states what a control does and stops.
  Login is a single centred card and its copy is operational rather than promotional.
- Vehicle deletion uses an explicit confirmation modal, removes the vehicle's uploaded
  photo, cascades dependent tracker credentials and telemetry in PostgreSQL, and leaves
  reusable dashboard widgets present but no longer pinned to the deleted vehicle.
- Vehicles have no propulsion classification in the UI, API or current schema. Garage,
  dashboards, history and widgets choose their presentation only from metric keys that
  are actually present; battery and fuel readings may coexist, and missing readings
  remain neutral rather than 0%.
- A garage card follows the arrangement vehicle-status cards converge on: photo across
  the top at a fixed ratio, then identity, then one labelled reading with its bar, then a
  short fact line and a relative contact time, with profile assignment and actions in a
  footer bar. A side thumbnail was tried and abandoned; that shape belongs to a list row.
  The fixed ratio keeps a card the same height before and after a photo is added. A
  vehicle reporting nothing lists nothing: an earlier card showed "current speed —",
  dressing an absence up as a reading.
- Presentation ranks metric keys by how universally they are reported: GNSS speed from
  the tracker, then standard OBD-II Mode 01 signals, then the optional fuel-level PID,
  then profile-only battery signals. A garage card leads with an energy level only when
  one is reported and otherwise promotes the most conventional reading the vehicle
  actually sends, so a standard OBD-II car no longer shows a permanently empty gauge.
  No surface offers a reading the vehicle has not reported.
- Telemetry is normalized (protocol v2, clean break, contract in
  `.agent/NORMALIZED_TELEMETRY_SPEC.md`): a sample is a transport envelope of
  independent observations (`key`, `value`, `observed_at`, `channel`, `method`),
  position is one atomic observation, and source identity comes only from
  authentication. Observations persist as indexed rows; per-(source, channel,
  metric) candidates feed a central resolver that alone selects live readings —
  validity, freshness, direct-over-derived, metric preferences (CAN/OBD speed
  over GNSS), then recency. The live API and SSE (envelope still version 1)
  return resolved reading objects with provenance and a `fresh` flag; widgets
  render, they never resolve. Freshness is cadence-aware: uploads declare a
  `reporting_interval` delivery promise (or `event_driven`, where silence means
  unchanged while the source stays in contact), candidates are judged by the
  promise they arrived under with registry windows as floors, and producers
  send null retractions when a channel dies rather than letting values age out.
  A quiet channel is not a dead one: a vehicle whose bus stops broadcasting while
  its adapter still answers is asleep, so the agent sends nothing and lets the
  values age, and retraction is reserved for hardware that has actually gone.
  Retained metrics (SOC, odometer, tyres…) degrade to visibly stale; transient
  or safety-sensitive ones (speed, charging) become unknown — absence is never
  false. Charging resolution lives server-side: fresh explicit
  `charging.active` is authoritative, otherwise derived from fresh power
  evidence over the shared floor, otherwise unknown; a derived `charging.power`
  is emitted when only `battery.power` evidence exists. Standard OBD PID `5B`
  is still sampled as a last-resort hybrid/EV pack charge, recorded in the
  validation ledger as unverified with unconfirmed semantics.
- History is dual-mode: the classic values/chart/route/entries experience over
  raw observations, plus a snapshot table (`/history/table?step_seconds=…`,
  steps 1 s–1 day) whose rows recreate the complete known car state newest to
  oldest, with forward-filled cells dimmed and age-labelled and quiet spans
  collapsed server-side. `/history/observations` exposes full per-observation
  provenance and feeds the raw report row disclosure. Hooks receive
  `ctx.telemetry.current`, `.triggering`, `.state_at(t)` (shared
  reconstruction with the table), and bounded `.history(...)`; the v1
  `ctx.telemetry.metrics`/`ctx.telemetry_batch` are gone and
  `docs/user-guide/hooks.md` documents the v2 context and its unknown-versus-false
  guards. The frontend uses
  bundled lucide icons behind a semantic `AppIcon` facade, and vehicle card
  actions are two icon+label controls with the destructive pair in the shared
  row menu. Verified: `./scripts/check.sh` exit 0 and Playwright browser e2e
  against the migrated v2 stack.
- Drive and charge segments are derived from lifecycle edges rather than a universal
  time-gap guess. The agent's recorded `vehicle_in_use` state keeps traffic stops inside
  one drive and closes it on the parked reading; explicit charging or charging-power
  signals keep a session continuous across the parked ten-minute cadence and close it on
  the first inactive reading. Vehicles without lifecycle signals retain the bounded
  speed/position fallback. A drive also needs motion evidence to exist (odometer
  advance, speed above the 1 km/h floor, or a position that moved): the C-Zero wakes
  its bus for a minute when the charger is unplugged and asserts in-use while doing
  so, which used to become a 0 km, 38-minute drive. Both segment kinds carry
  `unreported_seconds`, the sum of gaps wider than three times the row's declared
  cadence, so a 30 km drive whose agent was silent for most of its span says so
  instead of claiming the whole span as driving time.
- Profile computed metrics accept a `scale`, so the bundled C-Zero definition publishes
  `battery.power` in kilowatts. Agent, simulator and SPA now agree on that unit; they
  previously disagreed by a factor of a thousand.
- Widgets that can answer from current state offer an off-by-default hide-when-empty
  setting. Hidden widgets are dropped only in view mode and the canvas compacts to close
  the gap, so the premade Overview suits an EV, a fuel vehicle and a standard OBD-II car
  without editing. Editing always reveals every widget.
- Dashboards render as normal live pages; one overflow menu opens edit/create actions and
  edit mode adds controls directly to the same canvas. The versioned Overview is composed
  from ordinary selector, map, media, energy, telemetry, chart and tracker widgets and is
  added without removing older dashboards. Unpinned widgets react to the shared vehicle
  selector while explicitly pinned widgets remain fixed. The selector is a bounded,
  searchable dropdown for large fleets. Data widgets share a deliberate no-data state,
  avoid mounting empty maps/charts, and omit unavailable telemetry rows. XY charts split
  their line when the dominant x direction reverses, so separate charging sessions are
  never joined across an SOC reset, and x-monotone smoothing cannot bend the line back
  over itself. Time-series lines break wherever two samples are further apart than
  max(60 s, three times the series' median gap), so hours the source reported nothing
  are a hole in the line rather than a slow ramp between two readings; both charts take
  that median from one helper in chartData.ts. User-facing measurements share locale-aware formatting capped at two
  decimals by default; canonical precision and five-decimal coordinates remain explicit.
  History pairs the chart and route with a raw entries table: newest first, paginated
  rather than downsampled, sortable and numerically filterable on any column including
  profile-defined metrics, with per-vehicle column visibility and ordering persisted in
  the browser. Columns are derived from reported signals, so vehicles with different
  profiles show different columns. Vehicle and
  tracker creation use focused modals. Profiles have their own routed page, full-width
  profile rows, aligned vertical details, and distinct profile/signal modals with no
  artificial user-facing proof level. Hooks use a master-detail page: a rail holds the hook
  list and the account-wide secrets, and one detail panel carries a sticky
  enable/test/save bar above the settings, source and execution history, so nothing
  spans a width the rest of the page does not share. Hook creation uses a focused modal.
- Hook source is unrestricted Python, so it may import the standard library and the
  application's own runtime dependencies. Extra distributions are baked in at build time
  through the `VEHINODE_HOOK_PACKAGES` argument, because the container runs read-only and
  cannot install at runtime. The build applies the runtime lock as a constraint, so an
  added package that would move a pinned dependency fails the build instead of shipping
  an untested combination.
- Durable PostgreSQL jobs invoke trusted hooks in limited child processes outside API
  requests. Hooks have revisions, state, encrypted write-only secrets, redacted logs,
  HTTP/geometry helpers, manual dry-run and execution history.
- Catch-up uploads drain the durable agent outbox in independently acknowledged chunks of
  at most 200 samples. Ingestion independently splits those requests into hook triggers of
  at most 10 samples, leaving enough time for hooks that perform one external request per
  position, so a long outage cannot turn into one unbounded hook process. SDK version 3
  exposes the triggering observations, the
  current resolved state, shared state-at-time reconstruction and bounded raw history
  queries without pretending each sparse sample is a complete vehicle snapshot. Hook
  previews are bounded, complete structured logs are persisted separately and exposed
  through a paginated admin endpoint, HTTP response bodies and errors are capped, and an
  emergency result path reports memory exhaustion without trying to serialize the object
  that exhausted memory.
- The deployed vehicle agent is a standalone CGO-free Go executable. Versioned Linux
  builds cover ARMv6, ARMv7, ARM64 and AMD64; the bootstrap downloads the matching
  checksum-verified artifact without running `apt`, Python or a compiler on the tracker.
  It implements enrollment, a compiled-in offline SQLite outbox, remote last-known-good
  configuration, SIM7600 NMEA parsing, OBDLink/OBD support, safe profiles, CAN
  capture/replay, diagnostics, installation and systemd integration. Sampling is
  cadence-driven with event-triggered extras: a change in readiness, charging or
  reported state takes a debounced sample immediately and flushes the upload,
  stamped `sample_trigger` and leaving the declared cadence promise unchanged.
  The adapter's own supply reading is taken inside every listen burst (and every
  parked wake poll) as canonical `battery.aux_voltage` (channel obd), so each sample
  carries it whether or not the car's bus is awake, and it doubles as the probe that
  separates a sleeping bus from a missing adapter; three unanswered in a row is the
  adapter gone.
  Host-local hardware selection persists GPS, OBD and the cellular control port as
  `auto`, `off`, or a stable `/dev/serial/by-id` path. `auto` now probes: each candidate
  is opened and classified by what it answers (NMEA stream, ELM identity, AT modem),
  listening before writing so an unknown port is never sent a command. Name ranking was
  removed because one SIM7600 publishes five identically named interfaces and the old
  ordering chose a silent one. The agent enables GNSS over AT before reading, and falls
  back to polling `AT+CGPSINFO` when a module exposes no separate NMEA stream.
  `doctor --probe` reports each port's role and `monitor` prints live position and
  metrics together. The service records its resolved roles to `detection.json`, so
  `devices` and `doctor` report what it chose without competing for ports it already
  holds; probing again requires stopping the service first. Serial discovery is
  process-isolated: a timed-out open is killed and reaped before the next interface,
  and a failed sweep preserves the last working roles rather than erasing the only
  safe recovery route. If a proven NMEA stream genuinely stops, recovery escalates
  from a GNSS-only AT cycle to `AT+CRESET`, then to one USB reset of the configured receiver
  at most every 15 minutes; the CAN burst ladder ends in the same cooled-down reset for
  the adapter. Reset rights are not a vendor list: at install, update and `devices set`
  the agent resolves each configured tty through the sysfs walk to its USB
  vendor:product (and serial when present) and writes a udev rule granting the service
  group exactly those usb_device nodes, with autosuspend off for them; nothing else on
  the bus is granted, hubs are refused by device class even when named, and a tty that
  is not USB yields no rule and a warning naming what was found. The agent therefore
  works with whatever modem and adapter it was configured with (the owner's OBDLink SX
  is an FT-X, 0403:6015; a rule pinned to 6001 would have matched nothing). A fresh
  install runs one discovery sweep before starting the service so the first rule is
  not empty. An independent review on 2026-09-04 of the first cut of that ladder
  (ff85aee) found it granting every FTDI device, restarting its cooldown per
  acquisition, racing Close() into a fresh acquisition, starving the watchdog during a
  backlog upload, and (in its own first fix) escalating a slow stream exit into
  retracting the whole CAN channel; all were corrected and re-verified before that
  build was deployed. Valid NMEA traffic without a satellite fix is
  treated as a live receiver, not a hardware failure. The sweep persists through the
  wake-up commands a SIM7600 control port swallows after being opened, and every phase
  of the conversation reads against its own deadline so the watchdog derived from that
  budget cannot abandon a port that was about to answer. Those two together are what
  previously left a powered-down receiver with no interface able to switch it on, so
  only unplugging the board recovered it.
- Both position sources report how long they have been repeating a reading, published
  as `gps_fix_age_seconds` in agent health. A streamed fix ages when the receiver goes
  quiet, and a polled one ages when the module replays its last known position with a
  frozen clock, which SIMCom firmware does once the receiver loses the sky. A reading
  older than the freshness window is dropped rather than recorded as the current
  position, and that window scales with the sampling interval. Installation grants serial access and the executable
  retries and resumes interrupted downloads before checksum verification. The executable
  provides checksum-verified self-updates plus confirmation-gated complete removal of the
  service, executable, credentials and queued telemetry.
  Owners can create declarative profiles in the SPA; definitions are owner-scoped,
  server-validated, versioned with assigned agents, and validated again by the agent
  before replacing last-known-good configuration. Built-in profiles remain read-only.
- Production artifacts include a non-root multi-stage image, three-service Compose,
  CI/Pages/GHCR/release workflows, operator-focused VitePress docs and backup/restore
  scripts. A deployed server needs only the image-based Compose file and its private
  `.env`; it does not retain the source tree or require helper scripts. The Docker guide
  imports the canonical Compose file and documents direct backup/restore commands. A
  role-aware image entrypoint owns migrations and app/worker startup; Compose contains
  no project `name` or embedded shell startup pipeline. Vehicle photo bytes are capped
  at 25 MiB and stored in a dedicated filesystem volume; PostgreSQL stores metadata
  only, and the backup/restore procedure covers both stores.

## Verification

- Ruff and Ruff format pass across backend/agent; mypy passes for 106 source files in Linux.
- 227 backend/agent tests runnable without PostgreSQL pass on Linux, including vehicle photo
  validation/storage/ownership coverage and the complete
  simulator-to-hook E2E scenario plus custom-profile distribution and ownership.
- Frontend: ESLint and strict type check passing; 31 files / 257 behavior tests passing;
  production build passing. Table coverage includes metric-column sorting, numeric range
  filtering and per-vehicle column preferences.
- Playwright: 7 Chromium scenarios passing locally against a fresh migrated database,
  real API and worker. CI runs the same suite on PostgreSQL. They cover the primary
  product journey, idempotency, auth-realm isolation, live SSE state changes,
  environment-based admin bootstrap, rejection of later registration, file-backed photo
  upload with invariant card height, multiple/default dashboard persistence, mobile
  widget reflow, the routed profile/modal flow, browser-language detection, EN/FR,
  themes, metric-key-driven rendering
  and automated axe checks. The
  expanded stale-vehicle check found and fixed a light-theme status contrast defect. The
  composed dashboard selector also passes axe after correcting its grouped-button semantics.
  The axe passes caught three regressions introduced by the interface rewrite: a login page
  without an h1, card and widget headings skipping from h1 to h3, and a muted tone carrying
  real text below AA.
- The history entries endpoint guards its JSON sort/filter per dialect. The SQLite path is
  covered by tests; the PostgreSQL path is compile-verified only, since no PostgreSQL server
  was available in this environment.
- The NMEA provider drains every buffered sentence per sample and keeps the newest fix,
  discarding one older than a freshness window. It previously consumed one line per
  sample against a receiver emitting about ten per second, so the reported position fell
  progressively further behind the vehicle.
- The agent reads the CAN bus in bounded listen bursts, not a continuous stream: one
  second of filtered STM per sample while in use, plus a one-second wake poll each minute
  while parked so a drive start is noticed within a minute; bus-woke, bus-quiet and
  motion-onset events derive from the bursts. Every serial operation has a deadline and
  a tripped one escalates on the session goroutine (adapter reset and re-prepare, close
  and reopen, then a cooled-down USB reset of the OBDLink through the same usbrecovery
  the modem uses), so nothing on the sampling thread ever opens hardware: a read of
  either source is a snapshot, and acquisition runs on the retrying owners' goroutines.
  A loop watchdog dumps every goroutine's stack to the journal and exits if the run loop
  stalls, and the shipped unit carries Restart=always plus WatchdogSec fed from the loop
  heartbeat. This replaces continuous monitoring after 2026-09-04, when the loop froze
  four times for up to two hours each on a bus that was awake, released on a two-hour
  grid nobody has explained (no USB events, no timers), and SIGTERM waited for SIGKILL;
  the reference design is the owner's father's cron script, which listened for one
  second a minute from a reset adapter for years without a freeze. A sample waits for
  its own burst (bounded by the window plus 500 ms; a timeout returns the previous
  snapshot and says so in the provider state), so a reading is as fresh as the sample,
  and the in-use window is a third of the sampling interval clamped to 300 ms-1 s, so a
  1 s cadence is honest: every profile identifier repeats within 100 ms. `update` now
  rewrites the unit as well as the binary, which is what arms WatchdogSec on upgrades.
  A non-JSON server reply is now reported with status, content type, remote address,
  final URL and a 200-byte body preview, once per distinct signature: the same day's
  uploads all failed over cellular with a 2xx HTML page from the host holding the
  cars.grimbert.net certificate, and the old log line said only "invalid character '<'".
- The Go agent passes format, vet, unit tests and CGO-free cross-builds for all four
  release targets. Every packaged artifact has a matching verified SHA-256 checksum and
  the Linux AMD64 executable runs from the production image.
- VitePress build (including the repository Compose import), secret-file generation
  smoke test and Python server wheel build pass. Alembic upgrade/check/downgrade passes with
  the local SQLite migration smoke database.
- The committed lockfiles install from a fresh checkout and `scripts/check.sh` resolves
  the checkout directly; no prior editable installation is required for validation.
- The production image builds on Docker Desktop. Fresh installations run the single
  initial migration `3ce9a4d05b74`, which contains the final normalized v2 schema;
  app/PostgreSQL are healthy and the worker uses
  its role-appropriate no-HTTP health policy. The packaged image serves the bootstrap and
  all four standalone agent targets; lifecycle operations live in the executable. The
  browser suite passes against a disposable Linux image/SQLite app and worker. GitHub
  publication still requires the remote.

## Broken or failing

- No known runnable test or build failure.
- External validation remains: CI on GitHub, GHCR/Pages publication, backup/restore
  against a disposable deployment, and physical hardware/car.

## Hardware validation

- No hardware behavior is claimed physically verified. SIM7600, OBDLink and C-Zero
  paths are implementation/fixture-tested only; all C-Zero signals remain experimental.
  See `docs/agent/hardware-validation.md`.

## Exact next action

Exercise backup/restore against a disposable deployment. Run the GitHub workflows from
the remote repository. Validate hardware using the ledger without promoting experimental
signal status prematurely.
