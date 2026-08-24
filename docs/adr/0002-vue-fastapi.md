# ADR 0002: Vue SPA and FastAPI

Status: accepted (2026-08-23)

## Decision

Use Vue 3, strict TypeScript, Vite and Vue Router for a compiled SPA. Use FastAPI,
Pydantic and synchronous SQLAlchemy 2 services for the versioned JSON API. The final
runtime serves built assets and contains no Node tooling.

## Consequences

OpenAPI is the API source of truth. Route functions remain thin; blocking database
work runs in FastAPI's thread pool. One same-origin deployment simplifies sessions
and CSRF.
