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

Production needs few services and no Node runtime. The published application image
targets amd64 only: every extra platform rebuilds the entire image under emulation,
and the hub is a server workload. Running the hub on an ARM host means building the
image from the checkout. Agent releases are unaffected, because trackers run the
standalone executables of ADR 0007 rather than this image.
