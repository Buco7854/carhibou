# API

The generated OpenAPI document at `/api/openapi.json` is the source of truth; interactive
documentation is at `/api/docs`. Product routes are versioned under `/api/v1`.

Browser requests use the server session cookie. State-changing requests also send the
readable CSRF cookie value as `X-CSRF-Token`. Trackers use the separate
`Authorization: Device CREDENTIAL` scheme only on `/api/v1/device/*`.

Responses include `X-Request-ID`; callers may supply a well-formed request ID for trace
correlation. Validation errors use FastAPI's structured `detail` body. List/history
endpoints impose explicit bounds. Request bodies over the configured byte limit are
rejected before parsing.
