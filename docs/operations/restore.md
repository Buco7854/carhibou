# Restore

Start a new deployment with the original master key and compatible environment, then:

```sh
docker compose up -d postgres
./scripts/restore.sh ./backups/vehinode-YYYYmmddTHHMMSSZ.dump
docker compose run --rm app alembic upgrade head
docker compose up -d app worker
curl --fail http://localhost:8000/health/ready
```

Restore refuses a missing/non-file path and recreates the application database through
PostgreSQL tools. It is destructive to that named Compose database and therefore asks
for an explicit `--confirm` flag.

Afterward, sign in, load a vehicle history, inspect secret masks, run a dry-run hook and
verify a tracker can reconnect. Without the original `VEHINODE_MASTER_KEY`, database
rows remain intact but hook secrets cannot be decrypted.
