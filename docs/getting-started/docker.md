# Docker deployment

The production topology is intentionally three services: `app`, `worker`, and
`postgres`. App and worker use one non-root image and different commands. The compiled
Vue SPA is inside the image; Node is absent at runtime. PostgreSQL is not published to
the host by default.

The app runs `alembic upgrade head` before starting. The worker depends on app readiness.
Use a stable release tag rather than deploying a branch tip. See [deployment](../operations/deployment.md)
and [backups](../operations/backups.md) before storing real journeys.
