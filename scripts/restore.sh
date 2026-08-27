#!/bin/sh
set -eu

if [ "$#" -ne 2 ] || [ "$2" != "--confirm" ]; then
  echo "Usage: $0 BACKUP.dump --confirm" >&2
  echo "This replaces the Carhibou database in the current Compose deployment." >&2
  exit 2
fi
BACKUP=$1
if [ ! -f "$BACKUP" ]; then
  echo "Backup file does not exist: $BACKUP" >&2
  exit 2
fi

docker compose stop app worker
docker compose exec -T postgres dropdb --username carhibou --if-exists --force carhibou
docker compose exec -T postgres createdb --username carhibou --owner carhibou carhibou
docker compose exec -T postgres pg_restore --username carhibou --dbname carhibou --no-owner --exit-on-error < "$BACKUP"
echo "Database restored. Run migrations and start app/worker as documented."
