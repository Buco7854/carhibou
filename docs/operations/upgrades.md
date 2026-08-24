# Upgrades

Back up first. Pull a versioned image—not a mutable branch build—then apply migrations
before replacing app/worker processes:

```sh
docker compose pull
docker compose run --rm app alembic upgrade head
docker compose up -d app worker
curl --fail http://localhost:8000/health/ready
```

Review release notes for configuration changes. Database downgrades exist where
practical but restoring the pre-upgrade database backup is the reliable rollback for a
production failure. Upgrade Pi agents independently with
`vehinode-agent update --version X.Y.Z`.
