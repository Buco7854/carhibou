# Who sees what

Vehicles belong to the instance, not to a user. An administrator creates them and
decides, per vehicle and per person, what each account may do:

| Level     | Allows |
| --------- | ------ |
| *view*    | see the vehicle, its live state, its history, and place it on dashboards |
| *operate* | all of view, plus assign its profile, edit its agent's settings, enroll or remove its agents, and clear its recorded data |

Someone with no grants signs in to an empty vehicle list. There are no roles beyond
this: an account is either an administrator or it is what its grants say, vehicle by
vehicle. Administrators implicitly operate everything.

A vehicle you cannot see does not exist for you — not in lists, not in history, and
not as an error message that admits it is there.

## Profiles

Profiles are shared across the instance: everyone can see and assign the ones that
exist (assigning needs *operate* on the vehicle). Creating them is a separate
allowance an administrator grants per account. You can edit or delete only profiles
you created; administrators can manage all of them. Deleting a profile that vehicles
were using simply unassigns it from them.

## Hooks and secrets

Hooks run arbitrary Python inside the server, so hooks — and the secrets that exist
for them — are administrator-only. There is no per-vehicle hook permission.

## Dashboards

Dashboards are personal. Nobody else sees yours. A widget bound to a vehicle you can
no longer see shows its empty state rather than the vehicle.

## What new accounts start with

Administration holds a **default access** template: the profile-creation allowance
and a list of vehicle grants a newly created account receives. It is copied at
creation — editing the template later changes nothing for existing accounts, only
for accounts created afterwards. This is also what an account provisioned through
SSO starts with.

## Signing in with SSO

When the instance is configured for OpenID Connect (see the deployment
documentation), the login page offers a single-sign-on button beside the password
form. Accounts arriving through SSO are created automatically when auto-provisioning
is enabled, receive the default-access template, and are administrators exactly
while they are members of the configured admin group — membership is re-checked at
every login. The last active administrator is never demoted by a group change.
