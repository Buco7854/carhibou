# Installation

The supported server installation uses Docker Compose. It starts VehiNode, the hook
worker and PostgreSQL while keeping the database private to the Compose network.

## Before you start

You need:

- a Linux server with Docker Engine and the Docker Compose plugin;
- enough disk space for your telemetry history and backups;
- a hostname and TLS reverse proxy before exposing VehiNode to the internet.

For a first test on a trusted local network, `http://localhost:8000` is sufficient.

## Start VehiNode

```bash
git clone https://github.com/Buco7854/vehinode.git
cd vehinode
cp .env.example .env
./scripts/generate-secrets.sh --write .env
docker compose up -d --build
docker compose ps
curl -fsS http://localhost:8000/health/ready
```

The last command should return a ready status. Open `http://localhost:8000` and create
the first account. That first account receives administrator permissions, including
the privileged ability to manage Python hook code.

::: warning Before exposing VehiNode to the internet
Set `VEHINODE_ENVIRONMENT=production`, use your HTTPS origin for
`VEHINODE_PUBLIC_URL`, and set `VEHINODE_SESSION_COOKIE_SECURE=true`. After creating
the administrator account, set `VEHINODE_REGISTRATION_ENABLED=false` and restart the
app to close public registration. See the [production checklist](../operations/deployment.md).
:::

## Add your first vehicle

1. Sign in and create a vehicle.
2. Choose a vehicle profile only when it matches the physical vehicle. The C-Zero
   profile is experimental.
3. Open **Trackers**, choose **Add tracker**, and follow the generated command.

Enrollment tokens are short-lived and single-use. The permanent device credential is
issued directly to the agent and is never embedded in the installer URL.

## Useful next steps

- Read the complete [Docker Compose guide](./docker.md).
- Configure [backups](../operations/backups.md).
- Review [agent installation](../agent/installation.md) before preparing a Raspberry Pi.
