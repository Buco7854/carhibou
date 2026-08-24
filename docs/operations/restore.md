# Restore

Restore into an isolated or confirmed target deployment using the original `.env` and
`VEHINODE_MASTER_KEY`. The commands below replace the VehiNode database.

::: danger Confirm the target first
This procedure permanently deletes the `vehinode` database in the current Compose
project. Check `docker compose ls`, the working directory and the dump path before
continuing.
:::

```bash
dump_file=./backups/vehinode-YYYYmmddTHHMMSSZ.dump
test -s "$dump_file"

docker compose stop app worker
docker compose up -d postgres
docker compose exec -T postgres \
  dropdb -U vehinode --if-exists vehinode
docker compose exec -T postgres \
  createdb -U vehinode vehinode
docker compose exec -T postgres \
  pg_restore -U vehinode -d vehinode --exit-on-error --no-owner --no-privileges \
  < "$dump_file"
docker compose run --rm app alembic upgrade head
docker compose up -d app worker
```

Verify `/health/ready`, sign in, load a vehicle history, inspect secret masks, run a
dry-run hook and confirm that a tracker reconnects. Without the original
`VEHINODE_MASTER_KEY`, database rows remain intact but hook secrets cannot be decrypted.
