# Authentication

`User` owns vehicles and application resources. `AuthenticationIdentity` maps a local
email/password identity to that user; ownership never refers to a provider. The small
provider protocol contains `authenticate` and `link_identity`, leaving an OIDC provider
possible without migrating resource ownership.

Local passwords use Argon2id. Login creates an opaque browser token; only its keyed hash
is stored. Sessions expire, can be listed/revoked, and are invalidated by password
change. Cookies are HttpOnly, SameSite=Lax and Secure in production. Mutations require a
session-bound double-submit CSRF token.

Device credentials are independent hashes with an independent dependency. Passing a
device credential to a human route—or a browser cookie to a device route—fails.
