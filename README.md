# VehiNode

VehiNode is a self-hosted vehicle telemetry platform: a lightweight Raspberry Pi
agent durably uploads GPS, OBD-II, CAN and device-health samples to a FastAPI and
PostgreSQL modular monolith; a Vue SPA presents live state, history, configurable
dashboards and privileged Python hooks.

> Your vehicle produces data. You decide what that data does.

## Run with Docker

```bash
git clone https://github.com/Buco7854/vehinode.git
cd vehinode
cp .env.example .env
./scripts/generate-secrets.sh --write .env
docker compose up -d --build
curl -fsS http://localhost:8000/health/ready
```

Open `http://localhost:8000` and create the first administrator account. Before exposing
the service to the internet, configure HTTPS, secure cookies and closed registration as
described in the [installation guide](docs/getting-started/installation.md).

The full [`docker-compose.yml`](docker-compose.yml) and every setting are explained in
the [Docker Compose guide](docs/getting-started/docker.md).

## Develop VehiNode

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env
.venv/bin/alembic upgrade head
.venv/bin/uvicorn backend.app.main:app --reload
```

Run `npm ci && npm run dev` from `frontend/` in another terminal. Maintainer details
live in the [contributor guide](AGENTS.md) and [developer documentation](docs/developers/architecture.md),
separate from the operator-focused documentation navigation.

## Common checks

```bash
./scripts/check.sh
docker compose config
```

VehiNode is currently pre-1.0. Physical hardware support is implemented and
fixture-tested where stated, but hardware validation status is tracked honestly
in [docs/agent/hardware-validation.md](docs/agent/hardware-validation.md).
