# ADR 0006: Boring container deployment

Status: accepted (2026-08-23)

## Decision

Build the SPA in a Node stage, Python wheels in a builder, and run app or worker from
one minimal non-root Python image. Compose runs app, worker and PostgreSQL. The Pi
agent is a separately versioned artifact installed under systemd, never a container.
ADR 0007 supersedes the original Python packaging choice with standalone Go binaries.

The image entrypoint owns the stable `app` and `worker` roles. `app` migrates the
database before starting FastAPI; arbitrary commands pass through unchanged for
maintenance. Compose selects roles but does not duplicate application startup details.

## Consequences

Production needs few services and no Node runtime. The application image targets
amd64/arm64; agent releases follow the multi-architecture path defined by ADR 0007.
