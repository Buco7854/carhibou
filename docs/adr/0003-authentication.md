# ADR 0003: Authentication identities and separate device credentials

Status: accepted (2026-08-23)

## Decision

Ownership attaches to `users`. Provider-specific login data lives in
`auth_identities`; v1 implements `local`. Browsers use opaque, expiring server-side
sessions in HttpOnly SameSite cookies plus CSRF tokens. Devices use a separate hashed
credential and dependency that cannot authorize human routes.

Local registration is limited to the initial administrator while the user table is
empty. The same operation may run idempotently from bootstrap environment variables;
general local registration is not exposed after the first account exists.

## Consequences

OIDC can be added by linking another identity without migrating ownership. Session
revocation is immediate. Device enrollment uses short-lived, single-use tokens and
never places permanent credentials in installer URLs. Operators should remove bootstrap
credentials from the environment after the initial administrator signs in.
