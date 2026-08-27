# Changelog

All notable changes follow Keep a Changelog. Carhibou uses semantic versioning after
the first public release.

## [Unreleased]

### Added

- Complete FastAPI/PostgreSQL modular monolith with local sessions, device enrollment,
  idempotent telemetry, current state, history, dashboards and diagnostics.
- Privileged Python hook system with durable jobs, isolated execution, revisions,
  persistent state, encrypted secrets, helpers and execution history.
- Raspberry Pi agent, offline queue, simulator, SIM7600/OBDLink integrations, safe CAN
  profiles, capture/replay, installer and systemd unit.
- Vue 3 SPA using Tailwind, extensible English/French localization and persistent
  Light/Dark/Auto themes, plus history, maps, charts, dashboards and hook editor.
- Docker/Compose deployment, CI and release workflows, VitePress documentation,
  recipes, operations scripts and security guidance.
- Reproducible Playwright browser journey with axe accessibility checks, a disposable
  migrated database and the real FastAPI app plus worker.
- Authenticated Server-Sent Events for live owned-vehicle state with automatic browser
  reconnection, idle heartbeats and continued session validation.

### Changed

- Reworked the SPA into an original cobalt-accented live routebook with a restrained
  self-hosted login, custom node-route mark, modern open map, telemetry ledger,
  searchable garage roster and responsive light/dark themes.
- Dashboard responses now retain empty layout collections, and the standalone worker
  loads the complete SQLAlchemy model registry before polling jobs.
- Simplified the self-hosted login, removed redundant implementation facts, replaced
  fixed dashboard polling with live events and normalized status badges as rounded
  rectangles across desktop and mobile.
