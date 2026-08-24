#!/bin/sh
set -eu

DESTINATION=${1:-./backups}
case "$DESTINATION" in
  /|"$HOME"|"$HOME"/) echo "Refusing broad backup destination" >&2; exit 2 ;;
esac
mkdir -p "$DESTINATION"
chmod 0700 "$DESTINATION"
TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUTPUT="$DESTINATION/vehinode-$TIMESTAMP.dump"
umask 077
docker compose exec -T postgres pg_dump --username vehinode --format custom vehinode > "$OUTPUT"
if [ ! -s "$OUTPUT" ]; then
  echo "Backup is empty" >&2
  exit 1
fi
echo "Database backup created: $OUTPUT"
echo "Back up .env and VEHINODE_MASTER_KEY separately in encrypted storage."
