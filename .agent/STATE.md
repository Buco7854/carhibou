# Current project state

Updated: 2026-08-24

## Works

- The modular monolith implements local session authentication, vehicle ownership,
  one-time device enrollment, separate device credentials, idempotent telemetry,
  current state, bounded history, dashboards, diagnostics and explicit migrations.
  Local registration can create only the first administrator. That account can instead
  be bootstrapped idempotently from environment variables; later registration is always
  rejected and the identity boundary remains ready for a future OIDC provider.
- The Tailwind Vue SPA uses an original live-routebook workspace with a clear sidebar,
  continuous vehicle switcher, real route-first dashboard, telemetry ledger and
  photo-led searchable garage grid. Route/history charts, registry-based draggable
  dashboards, tracker administration, hooks and settings remain functional. Self-hosted
  IBM Plex typography, an original node-route mark, a modern neutralized OpenStreetMap treatment,
  optional owner-scoped vehicle photos with a plain missing-image placeholder, a
  cobalt recorded-route accent,
  extensible English/French catalogs and persistent Light, Dark and Auto themes work
  across the application. Login copy is operational and instance-focused rather than
  promotional. The live dashboard consumes an
  authenticated, session-revalidating SSE stream instead of browser polling, and its
  status badges keep a consistent rounded-rectangle shape at mobile widths.
- Garage, live dashboard, history and custom widgets share a canonical propulsion-aware
  display policy: EVs prioritize battery/charging, combustion vehicles fuel/engine data,
  hybrids available signals from both, and missing readings remain neutral rather than 0%.
- Durable PostgreSQL jobs invoke trusted hooks in limited child processes outside API
  requests. Hooks have revisions, state, encrypted write-only secrets, redacted logs,
  HTTP/geometry helpers, manual dry-run and execution history.
- The lightweight agent implements an offline SQLite queue, enrollment, remote
  last-known-good configuration, simulator, SIM7600 NMEA parsing, OBDLink/OBD support,
  safe profiles, CAN capture/replay, diagnostics, installer and systemd integration.
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

- Ruff, Ruff format, mypy: passing for 93 Python source files.
- Backend/agent tests runnable without PostgreSQL: 40 passing, including vehicle photo
  validation/storage/ownership coverage and the complete
  simulator-to-hook E2E scenario.
- Frontend: ESLint and strict type check passing; 6 files / 20 behavior tests passing;
  production build passing.
- Playwright: 2 Chromium scenarios passing locally against a fresh migrated database,
  real API and worker. CI runs the same suite on PostgreSQL. They cover the primary
  product journey, idempotency, auth-realm isolation, live SSE state changes,
  environment-based admin bootstrap, rejection of later registration, file-backed photo
  upload/dashboard display, persistent hook state, mobile reflow/badge geometry, EN/FR,
  themes, propulsion-aware EV/combustion rendering and automated axe checks. The
  expanded stale-vehicle check found and fixed a light-theme status contrast defect.
- VitePress build (including the repository Compose import), secret-file generation
  smoke test and Python wheel build pass. Alembic upgrade/check/downgrade passes with
  the local SQLite migration smoke database.
- The committed lockfiles install from a fresh checkout and `scripts/check.sh` resolves
  the checkout directly; no prior editable installation is required for validation.
- PostgreSQL integration and Docker image/Compose smoke cannot run locally because this
  runner has no PostgreSQL or container engine. Browser E2E is encoded in CI and runs
  locally; GitHub publication still requires the remote repository.

## Broken or failing

- No known runnable test or build failure.
- External validation remains: CI on GitHub, GHCR/Pages publication, real PostgreSQL and
  Docker execution, backup/restore against that deployment, and physical hardware/car.

## Hardware validation

- No hardware behavior is claimed physically verified. SIM7600, OBDLink and C-Zero
  paths are implementation/fixture-tested only; all C-Zero signals remain experimental.
  See `docs/agent/hardware-validation.md`.

## Exact next action

On a machine with Docker and PostgreSQL, run the deployment smoke flow in
`docs/operations/deployment.md`, then exercise backup/restore. Run the GitHub workflows
from the remote repository. Validate hardware using the ledger without promoting
experimental signal status prematurely.
