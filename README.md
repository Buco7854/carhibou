# Carhibou

Carhibou is a vehicle telemetry platform. A lightweight Raspberry Pi
agent durably uploads GPS, OBD-II, CAN and device-health samples; a FastAPI and
PostgreSQL server presents live state, history, dashboards and trusted Python hooks.

> Your vehicle produces data. You decide what that data does.

Read the [documentation](https://buco7854.github.io/carhibou/) for installation,
agent setup, hooks and operations.

## Run with Docker

```bash
mkdir -p carhibou && cd carhibou
curl -fsSL https://raw.githubusercontent.com/Buco7854/carhibou/main/docker-compose.yml \
  -o compose.yml
umask 077 && touch .env
```

Provide the database password, application keys, public URL and optional one-time
administrator credentials in `.env`, then run `docker compose up -d`. The
[installation guide](https://buco7854.github.io/carhibou/getting-started/installation)
contains the complete configuration, backup, restore and upgrade procedures.

## Develop Carhibou

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env
.venv/bin/alembic upgrade head
.venv/bin/uvicorn backend.app.main:app --reload
```

Run `npm ci && npm run dev` from `frontend/` in another terminal. Maintainer details
live in [AGENTS.md](AGENTS.md) and the
[architecture guide](https://buco7854.github.io/carhibou/developers/architecture).

Carhibou is pre-1.0. Physical support is tracked in the
[hardware validation ledger](docs/agent/diagnostics.md#hardware-validation-ledger);
fixture and simulator results are not physical proof.
