# Installation and operation

A normal Carhibou server needs only Docker Compose, a small environment file and two
persistent volumes. Put TLS in front of it before exposing it to the internet. The
published server image targets amd64; an ARM server can build the image from the
checkout. Vehicle agents use separate, native binaries on either architecture.

![First start: the sign-in page](/screens/login.png)

## Install with Docker Compose

```sh
mkdir -p carhibou
cd carhibou
curl -fsSL https://raw.githubusercontent.com/Buco7854/carhibou/main/docker-compose.yml \
  -o compose.yml
umask 077
touch .env
```

Generate the application keys and database password locally:

```sh
openssl rand -hex 32
openssl rand -base64 32 | tr '+/' '-_'
openssl rand -hex 24
```

Put the first value in `CARHIBOU_SESSION_PEPPER`, the second in
`CARHIBOU_MASTER_KEY`, and the third in `POSTGRES_PASSWORD`. The master key must decode
to exactly 32 bytes; never rotate it without the database, because it encrypts hook
secrets.

```dotenv
CARHIBOU_IMAGE=ghcr.io/buco7854/carhibou:latest
CARHIBOU_PORT=8000
CARHIBOU_ENVIRONMENT=production
CARHIBOU_PUBLIC_URL=https://vehicle.example.com
CARHIBOU_SESSION_COOKIE_SECURE=true

POSTGRES_PASSWORD=replace-with-a-random-database-password
CARHIBOU_SESSION_PEPPER=replace-with-at-least-32-random-characters
CARHIBOU_MASTER_KEY=replace-with-url-safe-base64-for-exactly-32-random-bytes

CARHIBOU_BOOTSTRAP_ADMIN_EMAIL=owner@example.com
CARHIBOU_BOOTSTRAP_ADMIN_PASSWORD=replace-with-a-strong-password
CARHIBOU_BOOTSTRAP_ADMIN_DISPLAY_NAME=Owner
```

`CARHIBOU_PUBLIC_URL` is an HTTP(S) origin without a path, query, credentials or
trailing slash. For a temporary HTTP-only trusted-LAN install, use `development`, the
real `http://` origin, and `CARHIBOU_SESSION_COOKIE_SECURE=false`. Keep `.env` readable
only by the operator.

Start the services and check readiness:

```sh
docker compose up -d
curl -fsS http://127.0.0.1:8000/health/ready
```

Compose runs `app`, `worker` and `postgres`. The app entrypoint migrates the database
before serving requests; the worker claims durable hook jobs. PostgreSQL lives in
`postgres-data`, and vehicle photos live in `vehicle-media`. `docker compose down -v`
deletes both volumes and is therefore not an ordinary restart command.

The bootstrap credentials create the first administrator idempotently and can never
create a later account. Sign in once, remove the three
`CARHIBOU_BOOTSTRAP_ADMIN_*` lines, and apply the environment again. Without bootstrap
variables, an empty instance shows the one-time setup form. Local registration closes
as soon as the first account exists.

Add a vehicle, select a matching telemetry profile only when its formulas and hardware
apply, then create an enrollment under **Data sources**. Before retaining useful data,
configure the backups below and [install the vehicle agent](/agent/agent).

### Single sign-on with OpenID Connect

OIDC is enabled when both issuer and client ID are present:

```dotenv
CARHIBOU_OIDC_ISSUER=https://sso.example.com/realms/home
CARHIBOU_OIDC_CLIENT_ID=carhibou
CARHIBOU_OIDC_CLIENT_SECRET=…             # optional for a public client
CARHIBOU_OIDC_SCOPES="openid email profile"
CARHIBOU_OIDC_GROUP_CLAIM=groups
CARHIBOU_OIDC_ADMIN_GROUP=carhibou-admins
CARHIBOU_OIDC_AUTO_PROVISION=true
CARHIBOU_OIDC_DISPLAY_NAME=Keycloak
```

Register `{CARHIBOU_PUBLIC_URL}/api/v1/auth/oidc/callback` at the provider. Authorization
code flow always uses PKCE. On return, Carhibou validates the provider signature,
issuer, audience and nonce, then resolves the linked provider subject. A verified email
may link an existing account; otherwise auto-provisioning must be enabled. New accounts
copy the default-access template. Membership in the configured administrator group is
re-evaluated at every login, but the last active administrator cannot be demoted.

## Production checklist

- Pin `CARHIBOU_IMAGE` to an exact release rather than a moving tag.
- Terminate TLS at a reverse proxy on the same browser origin and forward requests to
  the app port. Verify both `/health/live` and `/health/ready` through it.
- Check `docker compose ps`, app and worker logs, an agent upload, hook execution and
  the administration diagnostics after deployment.
- Back up PostgreSQL, vehicle media, `.env` and reverse-proxy configuration together.
- On an ARM server, build from the checkout with `docker build -t carhibou .` and set
  `CARHIBOU_IMAGE=carhibou`; published vehicle-agent artifacts are unaffected.

Hooks may import the Python standard library and the dependencies already in the
runtime. For additional packages, build a pinned custom image:

```sh
docker build --build-arg CARHIBOU_HOOK_PACKAGES="paho-mqtt==2.1.0" -t my-carhibou .
```

Set `CARHIBOU_IMAGE=my-carhibou`. The runtime lock is a build constraint, so an added
package cannot silently replace an application dependency.

## Back up

A restorable set contains the database dump, `vehicle-media`, `.env` (especially the
master key and session pepper), proxy configuration, and locally served versioned agent
artifacts that are unavailable from GitHub Releases. Store it away from the host and
test a restore periodically.

```sh
backup_stamp=$(date -u +%Y%m%dT%H%M%SZ)
umask 077
mkdir -p backups
docker compose stop app worker
docker compose exec -T postgres \
  pg_dump -U carhibou -d carhibou -Fc > "backups/carhibou-${backup_stamp}.dump"
docker compose run --rm --no-deps -T app python -c \
  'import sys, tarfile; a=tarfile.open(fileobj=sys.stdout.buffer, mode="w|gz"); a.add("/var/lib/carhibou/media", arcname="."); a.close()' \
  > "backups/carhibou-media-${backup_stamp}.tar.gz"
docker compose start app worker
test -s "backups/carhibou-${backup_stamp}.dump"
test -s "backups/carhibou-media-${backup_stamp}.tar.gz"
```

Stopping both writers gives the database and media one consistent boundary. Verify
`pg_restore --list` can read the dump and `tar -tzf` can read the archive.

## Restore

::: danger Destructive operation
These commands replace the current `carhibou` database and vehicle media. Confirm the
target Compose project and backup files first.
:::

```sh
dump_file=./backups/carhibou-YYYYmmddTHHMMSSZ.dump
media_file=./backups/carhibou-media-YYYYmmddTHHMMSSZ.tar.gz
test -s "$dump_file"
test -s "$media_file"
docker compose stop app worker
docker compose up -d postgres
docker compose exec -T postgres dropdb -U carhibou --if-exists carhibou
docker compose exec -T postgres createdb -U carhibou carhibou
docker compose exec -T postgres pg_restore -U carhibou -d carhibou \
  --exit-on-error --no-owner --no-privileges < "$dump_file"
docker compose run --rm --no-deps -T app python -c \
  'import pathlib, shutil, sys, tarfile; r=pathlib.Path("/var/lib/carhibou/media"); shutil.rmtree(r / "vehicle-photos", ignore_errors=True); a=tarfile.open(fileobj=sys.stdin.buffer, mode="r|gz"); a.extractall(r, filter="data"); a.close()' \
  < "$media_file"
docker compose run --rm app alembic upgrade head
docker compose start app worker
```

Restore the matching `.env` first. A wrong master key leaves database rows intact but
makes stored hook secrets unreadable. After startup, verify readiness, a vehicle history,
secret masks, photos, an agent upload and a harmless hook dry run.

## Upgrade and roll back

Take a verified backup, change `CARHIBOU_IMAGE` to the exact new version, then:

```sh
docker compose pull
docker compose up -d
docker compose ps
```

The app applies migrations before it becomes ready. Check both health endpoints and the
worker log. A reliable rollback is the old image plus the pre-upgrade database and media
backup; do not assume a newer schema is accepted by an older image. Agents upgrade
independently with `sudo carhibou-agent update --version X.Y.Z`.

## Troubleshooting

Start with `docker compose ps`, `docker compose logs app`, and
`docker compose logs worker`. Liveness proves the process answers; readiness also proves
its database dependency.

- A readiness failure after changing `POSTGRES_PASSWORD` often means the existing
  PostgreSQL volume still has the original password.
- Login or CSRF loops usually mean `CARHIBOU_PUBLIC_URL` does not match the browser
  origin, or secure cookies are being used over HTTP.
- Pending hooks need a healthy worker. A failed hook is not retried automatically because
  its external side effect may already have happened.
- A stale vehicle calls for `carhibou-agent doctor` and the systemd journal. Parked
  reporting may legitimately be slower than driving reporting.
- A GPS receiver that answers but has no fix usually needs a clearer view of the sky.
- Implausible CAN values require a verified profile formula, not a guessed correction.

## Short development setup

Development uses Python 3.13, Node 22 and Go 1.26. From the repository root:

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env
CARHIBOU_DATABASE_URL=sqlite:///./dev.db .venv/bin/alembic upgrade head
.venv/bin/uvicorn backend.app.main:app --reload
```

Run `npm ci && npm run dev` in `frontend/`, and `go test ./...` in `agent/`. The normal
pre-commit gate is `./scripts/check.sh`; PostgreSQL integration and browser E2E remain
the final check for behavior that differs from the local SQLite setup.
