# VehiNode

VehiNode is a self-hosted vehicle telemetry platform: a lightweight Raspberry Pi
agent durably uploads GPS, OBD-II, CAN and device-health samples to a FastAPI and
PostgreSQL modular monolith; a Vue SPA presents live state, history, configurable
dashboards and privileged Python hooks.

> Your vehicle produces data. You decide what that data does.

## Quick development start

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env
.venv/bin/alembic upgrade head
.venv/bin/uvicorn backend.app.main:app --reload
```

In another terminal:

```bash
cd frontend
npm ci
npm run dev
```

For a production-like deployment use `docker compose up --build`. See the
[documentation](docs/index.md), [security policy](SECURITY.md), and
[contributor guide](AGENTS.md).

## Common checks

```bash
./scripts/check.sh
docker compose config
```

VehiNode is currently pre-1.0. Physical hardware support is implemented and
fixture-tested where stated, but hardware validation status is tracked honestly
in [docs/agent/hardware-validation.md](docs/agent/hardware-validation.md).
