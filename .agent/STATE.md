# Current project state

Updated: 2026-08-24

## Works

- The modular monolith implements local session authentication, vehicle ownership,
  one-time device enrollment, separate device credentials, idempotent telemetry,
  current state, bounded history, dashboards, diagnostics and explicit migrations.
- The Tailwind Vue SPA implements live state, route/history charts, registry-based
  draggable dashboards, devices, hook administration and settings. English and French
  catalogs are extensible; Light, Dark and Auto themes persist locally.
- Durable PostgreSQL jobs invoke trusted hooks in limited child processes outside API
  requests. Hooks have revisions, state, encrypted write-only secrets, redacted logs,
  HTTP/geometry helpers, manual dry-run and execution history.
- The lightweight agent implements an offline SQLite queue, enrollment, remote
  last-known-good configuration, simulator, SIM7600 NMEA parsing, OBDLink/OBD support,
  safe profiles, CAN capture/replay, diagnostics, installer and systemd integration.
- Production artifacts include a non-root multi-stage image, three-service Compose,
  CI/Pages/GHCR/release workflows, VitePress docs and backup/restore scripts.

## Verification

- Ruff, Ruff format, mypy: passing for 90 Python source files.
- Backend/agent tests runnable without PostgreSQL: 33 passing, including the complete
  simulator-to-hook E2E scenario.
- Frontend: ESLint and strict type check passing; 5 files / 7 behavior tests passing;
  production build passing.
- VitePress build and Python wheel build pass. Alembic upgrade/check/downgrade passes
  with the local SQLite migration smoke database.
- PostgreSQL integration, Docker image/Compose smoke and GitHub publication are encoded
  in CI but cannot run locally because this runner has no PostgreSQL or container engine.

## Broken or failing

- No known runnable test or build failure.
- External validation remains: CI on GitHub, GHCR/Pages publication, real PostgreSQL and
  Docker execution, backup/restore against that deployment, and physical hardware/car.

## Hardware validation

- No hardware behavior is claimed physically verified. SIM7600, OBDLink and C-Zero
  paths are implementation/fixture-tested only; all C-Zero signals remain experimental.
  See `docs/agent/hardware-validation.md`.

## Exact next action

Run `./scripts/check.sh`, review the staged diff, and commit. On a machine with Docker,
run the deployment smoke flow in `docs/operations/deployment.md`; then validate hardware
using the ledger without promoting experimental signal status prematurely.
