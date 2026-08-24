# VehiNode implementation plan

## Phase 1 — usable vertical slice

- [x] Repository structure and durable project context
- [x] PostgreSQL models and Alembic migration
- [x] Local identity, sessions, CSRF, password change/revocation
- [x] Vehicle creation and ownership enforcement
- [x] One-time device enrollment and separate device authentication
- [x] Idempotent batch telemetry and atomic current state
- [x] Enrollable journey simulator
- [x] Responsive SPA login, vehicle creation and live dashboard
- [x] Tailwind design system, extensible i18n (English/French) and Light/Dark/Auto themes
- [x] Original live-routebook workspace, route-first dashboard and garage roster
- [x] Original node-route mark, instance-focused login and modern open map treatment

## Phase 2 — history and dashboards

- [x] Bounded/downsampled history and route API
- [x] History chart, route map and metric selection
- [x] Registry-based dashboard widgets with drag/resize/configuration
- [x] PostgreSQL dashboard persistence

## Phase 3 — Pi agent

- [x] Installer and systemd unit
- [x] SQLite queue, retry/catch-up and HTTP batch transport
- [x] Versioned last-known-good configuration
- [x] CLI diagnostics and simulated providers

## Phase 4 — physical integrations

- [x] SIM7600 NMEA provider and parser fixtures
- [x] OBDLink SX/STN adapter, standard OBD and reconnection
- [x] Portable CAN capture and offline replay
- [x] Safe declarative profile decoder and experimental C-Zero profile
- [x] Accurate hardware validation ledger
- [ ] Physical SIM7600, OBDLink SX and C-Zero validation (external hardware required)

## Phase 5 — hooks

- [x] Generic event envelope and PostgreSQL durable jobs
- [x] Hook CRUD, permissions and revision recovery
- [x] Child-process runtime, timeout/resource/log limits and crash recovery
- [x] Persistent state, encrypted secrets and central redaction
- [x] Stable context with HTTP, geometry, logging and dry-run helpers
- [x] Execution history, manual/retry APIs and SPA editor

## Phase 6 — recipes

- [x] Gate-on-arrival, Traccar and low-SOC hooks

## Phase 7 — production hardening

- [x] Multi-stage non-root Docker image and Compose definition
- [x] Health, diagnostics, structured/request-ID logging and payload limits
- [x] VitePress user/developer/operations documentation
- [x] CI, GitHub Pages, GHCR and versioned agent release workflows
- [x] Backup/restore scripts and security threat model
- [x] Full API/agent/hook end-to-end scenario and frontend behavior tests
- [x] Real-browser Playwright E2E with app/worker, mobile and accessibility coverage
- [x] Lockfile-based local CI-equivalent checks available in `scripts/check.sh`
- [ ] Real PostgreSQL, Docker image and Compose smoke (runner lacks both)
- [ ] GitHub Actions, Pages and GHCR publication (requires remote repository execution)
- [ ] Backup/restore exercise against a disposable PostgreSQL deployment
