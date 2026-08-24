# Backups

A restorable VehiNode backup set contains all of:

1. a PostgreSQL custom-format dump;
2. an archive of the file-backed `vehicle-media` volume;
3. the exact `VEHINODE_MASTER_KEY` used to encrypt hook secrets;
4. `.env` and reverse-proxy configuration;
5. any locally served versioned agent artifacts not retained in GitHub Releases.

## Create the database and media backup

No repository checkout or helper script is required:

```bash
umask 077
mkdir -p backups
backup_stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_file="backups/vehinode-${backup_stamp}.dump"
media_file="backups/vehinode-media-${backup_stamp}.tar.gz"

docker compose stop app worker
docker compose exec -T postgres \
  pg_dump -U vehinode -d vehinode -Fc > "$backup_file"
docker compose run --rm --no-deps -T app python -c \
  'import sys, tarfile; archive=tarfile.open(fileobj=sys.stdout.buffer, mode="w|gz"); archive.add("/var/lib/vehinode/media", arcname="."); archive.close()' \
  > "$media_file"
docker compose start app worker

test -s "$backup_file"
test -s "$media_file"
```

Stopping the writers keeps database metadata and media files in one consistent backup
set. The PostgreSQL dump does not contain image bytes.

Store `.env` separately in an encrypted secrets backup. Do not place it unencrypted
next to the database dump: together they contain the database password and the key that
decrypts hook secrets.

Copy both timestamp-matched files off the Docker host and periodically prove the
[restore procedure](./restore.md) on an isolated deployment. A successful `pg_dump`
command alone is not proof that the backup is recoverable.
