# ADR 0006: Boring container deployment

Status: accepted (2026-08-23)

## Decision

Build the SPA in a Node stage, Python wheels in a builder, and run app or worker from
one minimal non-root Python image. Compose runs app, worker and PostgreSQL. The Pi
agent is a versioned Python artifact installed under systemd, never a container.

## Consequences

Production needs few services and no Node runtime. The application image targets
amd64/arm64; ARMv6 agent releases follow a distinct path.
