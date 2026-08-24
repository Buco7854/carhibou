# Deployment

Copy `.env.example` to `.env`, replace every development value, then run:

```sh
docker compose up --build -d
docker compose exec app alembic upgrade head
curl --fail http://localhost:8000/health/ready
```

Compose runs only `app`, `worker` and `postgres`. App and worker use the same non-root
image; the image contains compiled SPA files and no Node runtime. PostgreSQL is internal
only. Put a TLS reverse proxy in front of port 8000 and set `VEHINODE_PUBLIC_URL` plus
secure cookies to that HTTPS origin.

Liveness checks only process health. Readiness queries PostgreSQL; optional hook target
services and vehicle connectivity do not affect it.
