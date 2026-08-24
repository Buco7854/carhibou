# Backups

A restorable VehiNode backup set contains all of:

1. a PostgreSQL custom-format dump;
2. the exact `VEHINODE_MASTER_KEY` used to encrypt hook secrets;
3. `.env`/deployment configuration, including session pepper and public URL;
4. any locally served versioned agent artifacts not retained in GitHub Releases.

Create a database dump from Compose:

```sh
./scripts/backup.sh ./backups
```

The script creates a timestamped `pg_dump` file with restrictive permissions. Copy the
environment/master key separately into an encrypted secrets backup; the script never
copies secrets automatically. Encrypt backups off-host and periodically prove restore
on an isolated deployment.
