# Authentication

`User` owns vehicles and application resources. `AuthenticationIdentity` maps a local
email/password identity to that user; ownership never refers to a provider. The small
provider boundary and provider-neutral identity table leave an OIDC provider possible
without migrating resource ownership.

Local passwords use Argon2id. Login creates an opaque browser token; only its keyed hash
is stored. Sessions expire, can be listed/revoked, and are invalidated by password
change. Cookies are HttpOnly, SameSite=Lax and Secure in production. Mutations require a
session-bound double-submit CSRF token.

Local registration is a one-time bootstrap boundary. `POST /auth/register` succeeds
only while the database contains no users and always creates the privileged initial
administrator. The same operation can run at app startup from
`VEHINODE_BOOTSTRAP_ADMIN_*`; it is idempotent and never adds a later user. General
local-user registration is intentionally unsupported. A future OIDC provider should
link identities through `AuthenticationIdentity`, not reopen the local bootstrap path.

Device credentials are independent hashes with an independent dependency. Passing a
device credential to a human route—or a browser cookie to a device route—fails.
