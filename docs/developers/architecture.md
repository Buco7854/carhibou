# Architecture

VehiNode is a modular monolith: one Python codebase provides a FastAPI process and a
PostgreSQL-backed worker process; both share one schema. The Vue 3 SPA is built by Vite
and served as static files from the production image. PostgreSQL is the only stateful
service. The vehicle agent is a separate CGO-free Go executable using an embedded SQLite
outbox, serial devices and HTTPS. Versioned builds cover Linux ARMv6, ARMv7, ARM64 and
AMD64 without requiring Python or a package manager on the agent.

Domain modules own their models, schemas, routes and services. Routes validate and
authorize; services own transactions and domain behavior. Alembic is the only
production schema creation mechanism.

Telemetry ingestion atomically stores history, updates current state, creates a generic
trigger and queues matching hook executions. The request then returns. The worker
claims jobs with `FOR UPDATE SKIP LOCKED` and executes each trusted hook in a bounded
child process. See the [architecture decisions](../adr/0001-modular-monolith.md).
