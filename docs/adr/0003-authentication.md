# ADR 0003: Authentication identities and separate device credentials

Status: accepted (2026-08-23)

## Decision

Ownership attaches to `users`. Provider-specific login data lives in
`auth_identities`; v1 implements `local`. Browsers use opaque, expiring server-side
sessions in HttpOnly SameSite cookies plus CSRF tokens. Devices use a separate hashed
credential and dependency that cannot authorize human routes.

## Consequences

OIDC can be added by linking another identity without migrating ownership. Session
revocation is immediate. Device enrollment uses short-lived, single-use tokens and
never places permanent credentials in installer URLs.
