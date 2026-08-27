# Carhibou security policy

Report suspected vulnerabilities privately to the repository security contact. Do not
open a public issue containing credentials, exploit details, personal location history,
or decrypted telemetry.

## Security model

Carhibou is designed for a trusted self-hosted household or organization, not mutually
untrusted SaaS tenants.

**Users with permission to modify Python hooks have privileged code-execution
capability in the Carhibou hook execution environment.** Child processes, timeouts,
memory limits and output caps contain mistakes and crashes; they are not a hostile-code
sandbox. Give `hooks.manage_code` only to administrators. Run the worker on networks
that privileged hooks are intentionally allowed to reach.

## Threat model and controls

- Browser passwords use Argon2id. Opaque, expiring sessions are hashed in PostgreSQL,
  sent only as HttpOnly SameSite cookies, individually revocable, and protected on
  state-changing requests by a double-submit token bound to the server session.
- Local registration is limited to an empty database and creates only the initial
  administrator. Optional environment bootstrap credentials are ignored after any user
  exists and should be removed from `.env` immediately after the first successful login.
  Provision the administrator before exposing an empty instance so another network
  client cannot win the one-time setup race.
- Authentication identities are separate from users/ownership so OIDC can be linked
  later. Agent credentials use a distinct `Authorization: Agent` realm and cannot
  authorize human routes. Tests enforce this isolation.
- Enrollment tokens are random, hashed, short-lived, single-use and vehicle-bound.
  Permanent credentials are shown only at enrollment/rotation and never placed in an
  installer URL. Revoke a tracker after suspected credential theft.
- TLS is mandatory outside localhost. A stolen active agent credential can impersonate
  that tracker and submit telemetry until revoked; it cannot read account data.
- Hook secrets use Fernet authenticated encryption under `CARHIBOU_MASTER_KEY`. Values
  are write-only in the API/UI and centrally redacted from hook logs/errors. Arbitrary
  privileged code can still deliberately exfiltrate secrets it is allowed to read.
- The master key is not stored in PostgreSQL. Losing it makes secrets unrecoverable;
  losing database plus key backups exposes them. Back up and restrict both separately.
- Vue escapes interpolation by default. Carhibou does not render telemetry or hook logs
  as HTML. Content Security Policy can be tightened at the reverse proxy; map tiles are
  the only default browser request to a third-party host.
- API payloads and batch sizes are bounded. Validation rejects invalid GPS coordinates,
  infinities, oversized names and duplicate IDs within a batch.
- Vehicle photos are owner-scoped JPEG, PNG or WebP files capped at 25 MiB and bounded
  by declared image dimensions. They are served through authenticated API routes from a
  private media directory, not a public static path. PostgreSQL stores metadata and a
  storage key, never the image bytes.
- Telemetry, state, triggers and jobs commit atomically. Hooks never run in the API.
  A crashed worker marks a leased execution failed for manual retry to avoid silently
  repeating external side effects.
- The installer accepts only HTTPS (except localhost), requests a fixed version, verifies
  a published SHA-256 digest, uses a dedicated system user, and installs no `main` branch.
  HTTPS plus the digest endpoint provides transport integrity; signed release artifacts
  are a future hardening option.
- Containers run non-root with no Docker socket, minimal writable paths and only the
  database network exposure they need. PostgreSQL is not published by default.
- Structured logs omit telemetry bodies and credentials at INFO. Authorization headers,
  plaintext secrets and passwords must never be added to diagnostics.

## Deployment checklist

1. Provide unique session pepper, PostgreSQL password and Fernet master key.
2. Serve only through trusted TLS and set `CARHIBOU_SESSION_COOKIE_SECURE=true`.
3. Restrict host/database ports and do not mount the Docker socket.
4. Keep the database, vehicle media, master key and environment configuration in
   encrypted backups.
5. Review hook administrators, active browser sessions and tracker inventory regularly.
6. Remove `CARHIBOU_BOOTSTRAP_ADMIN_*` after provisioning the first administrator.
7. Apply released security upgrades after testing backups and migrations.
