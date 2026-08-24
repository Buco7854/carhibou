# Backups

A restorable VehiNode backup set contains all of:

1. a PostgreSQL custom-format dump;
2. the exact `VEHINODE_MASTER_KEY` used to encrypt hook secrets;
3. `.env` and reverse-proxy configuration;
4. any locally served versioned agent artifacts not retained in GitHub Releases.

## Create the database dump

No repository checkout or helper script is required:

```bash
umask 077
mkdir -p backups
backup_file="backups/vehinode-$(date -u +%Y%m%dT%H%M%SZ).dump"
docker compose exec -T postgres \
  pg_dump -U vehinode -d vehinode -Fc > "$backup_file"
test -s "$backup_file"
```

Store `.env` separately in an encrypted secrets backup. Do not place it unencrypted
next to the database dump: together they contain the database password and the key that
decrypts hook secrets.

Copy backups off the Docker host and periodically prove the [restore procedure](./restore.md)
on an isolated deployment. A successful `pg_dump` command alone is not proof that the
backup is recoverable.
