# Carhibou

Carhibou is a self-hosted vehicle telemetry platform: a lightweight Raspberry Pi
agent durably uploads GPS, OBD-II, CAN and device-health samples to a FastAPI and
PostgreSQL modular monolith; a Vue SPA presents live state, history, configurable
dashboards and privileged Python hooks.

> Your vehicle produces data. You decide what that data does.

**[Documentation](https://buco7854.github.io/carhibou/)** — installation, agent setup,
hooks and operations.

## Run with Docker

```bash
mkdir -p carhibou && cd carhibou
curl -fsSL https://raw.githubusercontent.com/Buco7854/carhibou/main/docker-compose.yml \
  -o compose.yml
umask 077 && touch .env
```

Provide the database password, application keys, public URL and optional one-time
administrator credentials in `.env`, then run `docker compose up -d`. See the
[installation guide](https://buco7854.github.io/carhibou/getting-started/installation) for the complete file and
production settings.

The deployed directory contains only `compose.yml` and `.env`; source code and helper
scripts are not runtime requirements. The full [`docker-compose.yml`](docker-compose.yml)
is also embedded in the [Docker Compose guide](https://buco7854.github.io/carhibou/getting-started/docker).

## Develop Carhibou

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env
.venv/bin/alembic upgrade head
.venv/bin/uvicorn backend.app.main:app --reload
```

Run `npm ci && npm run dev` from `frontend/` in another terminal. Maintainer details
live in the [contributor guide](AGENTS.md) and [developer documentation](https://buco7854.github.io/carhibou/developers/architecture),
separate from the operator-focused documentation navigation.

## Common checks

```bash
./scripts/check.sh
docker compose --env-file .env.example config
```

Carhibou is currently pre-1.0. Physical hardware support is implemented and
fixture-tested where stated, but hardware validation status is tracked honestly
in [docs/agent/hardware-validation.md](docs/agent/hardware-validation.md).
