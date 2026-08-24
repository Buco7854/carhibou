# Upgrades

Back up first, set `VEHINODE_IMAGE` in `.env` to the new exact version, then pull and
replace the app and worker:

```sh
docker compose pull app worker
docker compose up -d app worker
curl --fail http://localhost:8000/health/ready
```

App startup applies migrations before accepting traffic. Review release notes for
configuration changes. Database downgrades exist where
practical but restoring the pre-upgrade database backup is the reliable rollback for a
production failure. Upgrade Pi agents independently with
`vehinode-agent update --version X.Y.Z`.
