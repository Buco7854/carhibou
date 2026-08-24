# Architecture

VehiNode is a modular monolith: one Python codebase provides a FastAPI process and a
PostgreSQL-backed worker process; both share one schema. The Vue 3 SPA is built by Vite
and served as static files from the production image. PostgreSQL is the only stateful
service. The Pi agent is a separate lightweight Python package using SQLite, serial and
HTTPS.

Domain modules own their models, schemas, routes and services. Routes validate and
authorize; services own transactions and domain behavior. Alembic is the only
production schema creation mechanism.

Telemetry ingestion atomically stores history, updates current state, creates a generic
trigger and queues matching hook executions. The request then returns. The worker
claims jobs with `FOR UPDATE SKIP LOCKED` and executes each trusted hook in a bounded
child process. See the [architecture decisions](../adr/0001-modular-monolith.md).
