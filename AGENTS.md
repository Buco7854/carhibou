# Carhibou agent guide

Carhibou is a self-hosted modular monolith for vehicle telemetry. The browser is
a Vue 3/TypeScript SPA; FastAPI owns HTTP and domain services; PostgreSQL owns
durable data and jobs; the worker runs trusted Python hooks in child processes;
the ARMv6-friendly Go agent uses serial devices, HTTP and a compiled-in SQLite queue.

## Invariants

- Human cookie sessions and device credentials are separate authentication realms.
- Local self-registration can create only the first administrator; later identities
  must never be created through the public registration endpoint.
- Telemetry writes, current-state updates, trigger creation, and job enqueueing are atomic.
- A hook never runs in an API request. Hook code is privileged, process-contained for
  reliability, and is not a hostile-code sandbox.
- Secrets are encrypted at rest, never returned after write, and centrally redacted.
- Vehicle-specific signals live in declarative profiles; never guess CAN formulas.
- Production schema changes use Alembic. Do not use `create_all()` in production.
- No Redis, Celery, message broker, GraphQL, microservices, or Node in runtime images.
- Physical validation claims must match `docs/agent/hardware-validation.md`.

## Repository map

- `backend/app/`: domain modules and the API; `backend/migrations/`: schema history.
- `frontend/`: Vue SPA and frontend tests.
- `agent/`: Pi agent, simulator, installer, profiles and tests.
- `docs/`: VitePress product/operations/developer documentation and ADRs.
- `.agent/`: concise working truth (`STATE.md`), plan, and temporary notes.

## Workflow and commands

At session start read this file, `.agent/STATE.md`, relevant `.agent/PLAN.md`,
`git status`, then only relevant code/tests. Work in vertical, tested increments.

```bash
./scripts/check.sh                 # all local lint/type/test/build checks
pytest backend/tests agent/tests   # Python/backend and reference-fixture tests
cd agent && go test ./... && go vet ./...
ruff check . && ruff format --check . && mypy backend agent
cd frontend && npm test && npm run typecheck && npm run build
cd frontend && npx playwright install chromium && npm run test:e2e
cd docs && npm ci && npm run docs:build
alembic upgrade head
python -m backend.app.worker --once
go run ./agent/cmd/carhibou-agent --help
```

Before a cohesive commit: run focused tests, inspect the diff, update docs plus
`.agent/STATE.md` and `.agent/PLAN.md`, then commit. Keep `STATE.md` under about
200 lines. Full completion means all items in `.agent/PLAN.md` and the validation
checklist in `docs/developers/definition-of-done.md` pass; scaffolding and mocked
core flows never count. Key decisions are in `docs/adr/`.
