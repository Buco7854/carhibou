# Docker Compose

A normal VehiNode server directory stays deliberately small:

```text
vehinode/
├── compose.yml
└── .env
```

The source tree and helper scripts are not runtime dependencies. Compose pulls the
published application image, which already contains the API, worker code, migrations
and compiled Vue interface.

## Services

| Service | Purpose | Host access |
| --- | --- | --- |
| `app` | Web interface, API and database migrations | Port `8000` by default |
| `worker` | Durable jobs and isolated Python hook execution | None |
| `postgres` | Telemetry, users, configuration and jobs | None |

The `app` and `worker` services use the same non-root image. Node is not present at
runtime, and PostgreSQL is not exposed to the host.

The image entrypoint exposes explicit `app` and `worker` roles. The default `app` role
applies Alembic migrations before starting FastAPI; Compose only selects `worker` for
the background service instead of embedding shell startup pipelines.

## Required environment

Compose refuses to start without the database password, session pepper, master key and
public URL. Supply them in `.env`:

| Setting | Purpose |
| --- | --- |
| `VEHINODE_IMAGE` | Exact GHCR release tag; defaults to `latest` |
| `VEHINODE_PUBLIC_URL` | Browser origin and base for tracker enrollment URLs |
| `VEHINODE_SESSION_PEPPER` | Random value of at least 32 characters |
| `VEHINODE_MASTER_KEY` | URL-safe base64 encoding of exactly 32 random bytes |
| `POSTGRES_PASSWORD` | Password shared by the app and private PostgreSQL service |
| `VEHINODE_BOOTSTRAP_ADMIN_*` | Optional one-time initial administrator credentials |

Do not rotate `VEHINODE_MASTER_KEY` independently of the database. Existing hook
secrets cannot be decrypted without the key that encrypted them.

## Start and inspect

```bash
docker compose pull
docker compose up -d
docker compose ps
docker compose logs -f app worker
```

The app applies Alembic migrations before accepting traffic. Press
<kbd>Ctrl</kbd>+<kbd>C</kbd> to stop following logs; the containers continue running.

## Initial administrator

When both `VEHINODE_BOOTSTRAP_ADMIN_EMAIL` and
`VEHINODE_BOOTSTRAP_ADMIN_PASSWORD` are present, app startup creates the administrator
only if the database contains no users. Existing databases are never changed by these
variables. Remove the bootstrap credentials from `.env` after the first successful
login and recreate the services with `docker compose up -d`.

Without those variables, an empty instance exposes the initial setup form. After the
first account is created, the setup endpoint reports registration closed and all later
registration requests are rejected. Future OIDC identities can use the existing
identity boundary without reopening local registration.

## Canonical Compose file

This page includes the canonical [`docker-compose.yml`](https://github.com/Buco7854/vehinode/blob/main/docker-compose.yml)
directly from the repository.

<<< ../../docker-compose.yml

## Data and lifecycle

PostgreSQL data lives in the named volume `postgres-data`. These commands preserve it:

```bash
docker compose stop
docker compose start
```

Apply edits to `.env` with `docker compose up -d`.

::: danger Do not delete the database volume casually
`docker compose down -v` deletes the PostgreSQL volume and all telemetry stored only
there. Take and verify a [backup](../operations/backups.md) first.
:::

Building the image from a source checkout is a developer workflow, documented
separately in [Development](./development.md). It is not required to operate VehiNode.
