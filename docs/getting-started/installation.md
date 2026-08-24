# Installation

The server installation needs only two files in its own directory: the Compose file
and your private environment file. It does not require a source checkout, Python or
Node.

## Before you start

Install Docker Engine with the Docker Compose plugin. Use a hostname and TLS reverse
proxy before exposing VehiNode to the internet.

## Create the deployment directory

```bash
mkdir -p vehinode
cd vehinode
curl -fsSL https://raw.githubusercontent.com/Buco7854/vehinode/main/docker-compose.yml \
  -o compose.yml
umask 077
touch .env
```

For a long-lived deployment, download `compose.yml` from the same release tag as the
container image instead of tracking `main`.

## Provide the configuration

Open `.env` in your editor and provide your own values:

```dotenv
VEHINODE_IMAGE=ghcr.io/buco7854/vehinode:latest
VEHINODE_PORT=8000
VEHINODE_ENVIRONMENT=production
VEHINODE_PUBLIC_URL=https://vehicle.example.com
VEHINODE_SESSION_COOKIE_SECURE=true

POSTGRES_PASSWORD=replace-with-a-random-database-password
VEHINODE_SESSION_PEPPER=replace-with-at-least-32-random-characters
VEHINODE_MASTER_KEY=replace-with-url-safe-base64-for-exactly-32-random-bytes

VEHINODE_BOOTSTRAP_ADMIN_EMAIL=owner@example.com
VEHINODE_BOOTSTRAP_ADMIN_PASSWORD=replace-with-a-strong-password
VEHINODE_BOOTSTRAP_ADMIN_DISPLAY_NAME=Owner
```

You can bring keys from your existing secret manager. If you need to generate new
values without downloading a VehiNode script, common OpenSSL commands are:

```bash
openssl rand -hex 32
openssl rand -base64 32 | tr '+/' '-_'
openssl rand -hex 24
```

Use the first value as the session pepper, the second as the master key, and the third
as the PostgreSQL password. Keep `.env` readable only by the deployment owner.

For an HTTP-only test on a trusted LAN, use `VEHINODE_ENVIRONMENT=development`, set
`VEHINODE_PUBLIC_URL` to the actual `http://` origin, and set
`VEHINODE_SESSION_COOKIE_SECURE=false`.

## Start VehiNode

```bash
docker compose pull
docker compose up -d
docker compose ps
curl -fsS https://vehicle.example.com/health/ready
```

The environment credentials create the initial administrator before VehiNode accepts
traffic. This bootstrap is idempotent: once any user exists, it never creates another.
After confirming that you can sign in, remove the three
`VEHINODE_BOOTSTRAP_ADMIN_*` lines from `.env` and run `docker compose up -d` again.

If you omit the bootstrap credentials on an empty database, the login page offers a
one-time initial-administrator form. Registration closes permanently as soon as that
account exists; VehiNode does not provide general local-user registration.

## Add your first vehicle

1. Sign in and create a vehicle.
2. Choose a vehicle profile only when it matches the physical vehicle. The C-Zero
   profile is experimental.
3. Open **Trackers**, choose **Add tracker**, and follow the generated command.

Enrollment tokens are short-lived and single-use. The permanent device credential is
issued directly to the agent and is never embedded in the installer URL.

Next, read the [Docker Compose guide](./docker.md), configure
[backups](../operations/backups.md), and review the [agent installation](../agent/installation.md).
