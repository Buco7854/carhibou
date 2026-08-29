# Who sees what

Vehicles belong to the instance. An administrator creates them and decides, per vehicle
and per person, what each account may do.

![Administration: people, grants and the default-access template](/screens/admin.png)

| Level | Allows |
| --- | --- |
| *view* | See the vehicle, live state and history, and place it on dashboards |
| *operate* | Everything in view, plus assign its profile, edit its agent settings, enroll or remove agents, and clear recorded data |

Someone with no grants signs in to an empty vehicle list. There are no other ordinary
roles: an account is either an administrator or it is what its grants say, vehicle by
vehicle. Administrators implicitly operate everything.

An invisible vehicle does not exist for that person, not in lists, history, or an error
message that admits it is there.

## Profiles

Profiles are shared across the instance, so everyone can see them. Assigning one to an
agent or connector needs *operate* on its vehicle. Creating profiles is a separate
allowance an administrator grants per account. A creator may edit or delete their own
profiles; administrators may manage all of them. Deleting an assigned profile silently
unassigns it from those data sources.

## Hooks, secrets and dashboards

Hooks run arbitrary Python in the server environment, so hooks and their secrets are
administrator-only. There is no per-vehicle hook permission.

Dashboards are personal. Nobody else sees yours. A widget bound to a vehicle you can no
longer see shows its empty state instead of revealing the vehicle.

## New accounts

Administration holds a **default access** template: the profile-creation allowance and
vehicle grants copied to each newly created account. Changing the template affects only
future accounts, including accounts auto-provisioned through SSO.

Public local registration creates only the first administrator and then remains closed.
Later accounts come from an administrator or OIDC auto-provisioning. The last active
administrator cannot be demoted, suspended or deleted, and an administrator cannot
remove their own access. Suspending an account invalidates its open sessions immediately.

## Signing in with SSO

When [OpenID Connect is configured](/getting-started/installation#single-sign-on-with-openid-connect),
the login page offers its provider beside the password form. Identity is linked by
provider subject, or by a verified email match. New accounts require auto-provisioning
and receive the default-access template. Membership in the configured administrator
group is re-checked on every login; the last active administrator is never demoted by a
group change.
