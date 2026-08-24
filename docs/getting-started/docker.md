# Docker Compose

VehiNode runs as one Docker Compose project with three services:

| Service | Purpose | Host access |
| --- | --- | --- |
| `app` | Web interface, API and database migrations | Port `8000` by default |
| `worker` | Durable jobs and isolated Python hook execution | None |
| `postgres` | Telemetry, users, configuration and jobs | None |

The `app` and `worker` services use the same non-root image. The compiled Vue
application is already inside that image; Node is not present at runtime.

## Configuration

Create the environment file once and keep it out of version control:

```bash
cp .env.example .env
./scripts/generate-secrets.sh --write .env
```

The command replaces the database password, session pepper and master encryption key,
then restricts `.env` to the current user. Edit these settings for the deployment:

| Setting | Local test | Internet-facing server |
| --- | --- | --- |
| `VEHINODE_ENVIRONMENT` | `development` | `production` |
| `VEHINODE_PUBLIC_URL` | `http://localhost:8000` | Exact public HTTPS origin |
| `VEHINODE_SESSION_COOKIE_SECURE` | `false` | `true` |
| `VEHINODE_REGISTRATION_ENABLED` | `true` | `true` for first account, then `false` |
| `VEHINODE_PORT` | `8000` | Host port used by your reverse proxy |
| `VEHINODE_IMAGE` | `vehinode:local` | A pinned release image, when available |

Do not rotate `VEHINODE_MASTER_KEY` independently of the database. Existing hook
secrets cannot be decrypted without the key that encrypted them.

## Build and start from the repository

```bash
docker compose up -d --build
docker compose ps
curl -fsS http://localhost:8000/health/ready
```

The app applies Alembic migrations before accepting traffic. Follow startup with:

```bash
docker compose logs -f app worker
```

Press <kbd>Ctrl</kbd>+<kbd>C</kbd> to stop following logs; the containers continue to run.

## Use a published image

When installing a tagged release, set `VEHINODE_IMAGE` in `.env` to its exact GHCR
tag instead of a mutable branch image. Then run:

```bash
docker compose pull app worker
docker compose up -d --no-build
```

## Compose file

This page includes the canonical [`docker-compose.yml`](https://github.com/Buco7854/vehinode/blob/main/docker-compose.yml)
directly from the repository, so it cannot silently drift from the file users run.

<<< ../../docker-compose.yml

## Data and lifecycle

PostgreSQL data lives in the named volume `postgres-data`. Normal stop and restart
commands preserve it:

```bash
docker compose stop
docker compose start
```

To apply configuration after editing `.env`:

```bash
docker compose up -d
```

::: danger Do not delete the database volume casually
`docker compose down -v` deletes the PostgreSQL volume and all telemetry stored only
there. Take and verify a [backup](../operations/backups.md) first.
:::

Before using VehiNode outside a trusted LAN, complete the [production checklist](../operations/deployment.md).
