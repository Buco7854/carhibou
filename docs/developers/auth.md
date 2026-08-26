# Authentication

Vehicles belong to the instance; what a `User` may do with one is a per-vehicle
grant, resolved by the access module (`backend/app/access/`) and nowhere else.
`AuthenticationIdentity` maps a provider identity (local password, or OIDC) to the
user; grants never refer to a provider. Dashboards remain the one personal,
per-user resource.

Local passwords use Argon2id. Login creates an opaque browser token; only its keyed hash
is stored. Sessions expire, can be listed/revoked, and are invalidated by password
change. Cookies are HttpOnly, SameSite=Lax and Secure in production. Mutations require a
session-bound double-submit CSRF token.

Local registration is a one-time bootstrap boundary. `POST /auth/register` succeeds
only while the database contains no users and always creates the privileged initial
administrator. The same operation can run at app startup from
`VEHINODE_BOOTSTRAP_ADMIN_*`; it is idempotent and never adds a later user. General
local-user registration is intentionally unsupported: after the bootstrap, accounts
come from an administrator or from OIDC auto-provisioning, both of which copy the
default-access template. OIDC links identities through `AuthenticationIdentity` and
never reopens the local bootstrap path.

Device credentials are independent hashes with an independent dependency. Passing a
device credential to a human route—or a browser cookie to a device route—fails.

## Adding people after the first account

Public registration only ever creates the first administrator, so later identities come
from the administrator endpoints under `/api/v1/users`, gated on `system.admin`. They
create an account, suspend or restore it, grant or revoke administration, and delete it.

Two rules keep an instance recoverable. The last active administrator can never be
demoted, suspended or deleted, because nobody would be left who could restore access and
registration will not reopen. An administrator also cannot remove their own access, which
turns the most likely accidental lockout into a plain error.

Suspending is immediate and complete: `is_active` is checked at sign-in, on every
authenticated request and on the event stream, so an open session stops working rather
than surviving until it expires.

Deleting an account deletes what it owned. Vehicles, telemetry, agents and hooks cascade
in the database, and the interface says so before asking for confirmation.

## Administration is a separate page

Managing people, clearing recorded data and reading system health are not
preferences, and sat beside them only because both were called settings. They are
their own page now, reachable and routable only by an administrator, so an ordinary
account sees a settings page that is entirely about itself.
