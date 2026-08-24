# Production checklist

Use this checklist after the local Docker installation works and before exposing
VehiNode outside a trusted network.

## Pin what you deploy

Deploy a reviewed release tag or commit. If a GHCR release image is available, set its
exact tag in `VEHINODE_IMAGE`; avoid relying on a mutable branch image for data you care
about.

## Configure the public origin

Put a TLS reverse proxy in front of the app and use the same origin for the SPA and API.
Set the following values in `.env`:

```dotenv
VEHINODE_ENVIRONMENT=production
VEHINODE_PUBLIC_URL=https://vehicle.example.com
VEHINODE_SESSION_COOKIE_SECURE=true
```

`VEHINODE_PUBLIC_URL` must be an HTTP(S) origin without credentials, path, query or
fragment. It is also used to generate agent enrollment URLs, so it must be reachable by
the vehicle tracker.

## Bootstrap the administrator once

Set `VEHINODE_BOOTSTRAP_ADMIN_EMAIL`, `VEHINODE_BOOTSTRAP_ADMIN_PASSWORD` and optionally
`VEHINODE_BOOTSTRAP_ADMIN_DISPLAY_NAME` before the first start. VehiNode consumes those
values only when the database has no users. After the first successful login, delete
the bootstrap values from `.env` and recreate the services:

```bash
docker compose up -d app worker
```

There is no registration switch to reopen. The browser registration endpoint creates
only the initial administrator and rejects every request after a user exists. A future
OIDC provider can add identities through the provider boundary without enabling general
local registration.

## Verify the deployment

```bash
docker compose ps
curl --fail https://vehicle.example.com/health/live
curl --fail https://vehicle.example.com/health/ready
docker compose logs --tail=100 app worker
```

`/health/live` confirms that the web process responds. `/health/ready` also checks the
PostgreSQL connection. Optional hook targets and vehicle connectivity do not affect
readiness.

In the administration diagnostics page, confirm that the database is healthy, the
worker heartbeat is current, and no jobs are unexpectedly pending or failed.

## Make recovery possible

Back up all of these together:

- the PostgreSQL database;
- the file-backed `vehicle-media` volume containing uploaded vehicle photos;
- `.env`, especially `VEHINODE_MASTER_KEY` and `VEHINODE_SESSION_PEPPER`;
- reverse-proxy and deployment configuration.

Follow the [backup](./backups.md) and [restore](./restore.md) guides, then test a restore
on an isolated deployment before depending on it.
