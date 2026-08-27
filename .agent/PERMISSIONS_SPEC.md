# VehiNode access model — implementation contract

This is the single source of truth for the permission rework. Every decision here
was made by the product owner; do not relitigate them. Backward compatibility is
explicitly NOT required, but Alembic migrations must still bring an existing
database forward without data loss.

## The model

There are exactly two account-level permissions, and no roles:

- `system.admin` — manages the instance: users, vehicles, hooks, secrets, grants,
  the default-access template, system diagnostics, clearing all data.
- `profiles.create` — may create vehicle profiles, and edit/delete only the
  profiles they themselves created.

Everything else is a per-vehicle grant, assigned by an admin:

| Level     | Allows |
| --------- | ------ |
| `view`    | see the vehicle, its live state, history/telemetry, put it on dashboards |
| `operate` | all of view, plus: assign/unassign its profile, edit its agent settings, enroll/rotate/revoke/delete its agents, clear its telemetry |

An admin implicitly has `operate` on every vehicle. A user with no grants sees an
empty vehicle list (this replaces the old "guest" idea — no separate role).

## Vehicles

- `Vehicle.owner_id` is REMOVED. Vehicles belong to the instance.
  Add `created_by` (nullable FK users.id, ondelete SET NULL) as audit only —
  nothing filters on it.
- Create vehicle: admin only. Delete vehicle: admin only.
- `DELETE /vehicles/telemetry` (all vehicles): admin only.
- `DELETE /vehicles/{id}/telemetry`: operate.
- Photo upload/delete: operate.
- `VehicleResponse` gains `access: "view" | "operate"` — the caller's effective
  level (admin ⇒ "operate"). The frontend gates buttons on this.

## Profiles

- All profiles are instance-wide and visible to every authenticated user.
  `VehicleProfile.owner_id` becomes `created_by` (nullable, SET NULL).
- Create: admin or `profiles.create`.
- Edit/delete: admin, or the creator (non-built-in only). Built-ins stay read-only.
- Deleting a profile that is assigned to vehicles silently unassigns it from ALL
  of them (bump each affected device's config_version, as assign_profile already
  does). The deleting user is NOT told which or whether vehicles used it — no
  count, no warning, plain 204. This is deliberate: it must not leak the
  existence of vehicles the user cannot see.
- A creator deleted → profile survives with created_by NULL (admin-manageable).
- `VehicleProfileResponse` gains `editable: bool` (computed server-side for the
  caller: admin, or created_by == caller, and not built-in).

## Hooks and secrets

- All hook routes and all secret routes: admin only. Hook `owner_id` semantics
  collapse: hooks are instance resources (keep a `created_by` audit column if a
  rename is cheap; otherwise keep the column name but stop filtering on it —
  prefer the rename since compat is not required).
- Secrets become instance-wide: drop owner scoping, unique on name alone.
  Migration: on duplicate names keep the most recently updated row.
- Hook runtime (`hooks/runtime.py`): ctx.secrets reads the instance set; the
  vehicle filter on a hook stays as-is.

## Dashboards

Dashboards remain PERSONAL resources — keep their per-user scoping exactly as it
is. A widget bound to a vehicle the user cannot see renders its empty state
(frontend already handles an absent vehicle). Do not convert dashboards to grants.

## Default-access template

- New single-row storage (suggest `app_settings` key/value JSON table; key
  `default_access`), admin-editable:
  `{ "profiles_create": bool, "grants": [{"vehicle_id": str, "level": "view"|"operate"}] }`
- COPIED at user creation (both admin-created and OIDC-provisioned) — never live.
  Editing the template affects only future users. Grants referencing a deleted
  vehicle are skipped at apply time.
- Endpoints: `GET /admin/default-access`, `PUT /admin/default-access` (admin).

## Users

- Keep `is_admin`, `is_active`, existing last-admin guards (`_guard_last_admin`).
- Add `can_create_profiles: bool` column (default false).
- The permissions map already exposed to the frontend gains `profiles.create`.
- `PATCH /users/{id}` accepts `can_create_profiles`.
- Grants management is vehicle-centric:
  - `GET /vehicles/{id}/access` (admin) → `[{user_id, email, display_name, level}]`
  - `PUT /vehicles/{id}/access` (admin) → full replacement list `[{user_id, level}]`
- Deleting a user cascades their grants (FK CASCADE), sets created_by NULL on
  vehicles/profiles they created. The old user→vehicles ownership relationship
  is removed.

## OIDC

Env-configured (all optional; feature off unless issuer+client set):

```
VEHINODE_OIDC_ISSUER, VEHINODE_OIDC_CLIENT_ID, VEHINODE_OIDC_CLIENT_SECRET,
VEHINODE_OIDC_SCOPES (default "openid email profile"),
VEHINODE_OIDC_GROUP_CLAIM (default "groups"),
VEHINODE_OIDC_ADMIN_GROUP (group whose members are admins),
VEHINODE_OIDC_AUTO_PROVISION (default true),
VEHINODE_OIDC_DISPLAY_NAME (login button label, default "SSO")
```

- Standard authorization-code flow with discovery, state + nonce (+ PKCE).
  Use a well-maintained library (authlib preferred); pin it in pyproject AND
  requirements-backend.lock.
- Identity linking: the existing `AuthenticationIdentity` table, provider
  `"oidc"`, subject = `sub`. Match existing users by identity first, then by
  verified email; otherwise auto-provision (if enabled) applying the
  default-access template.
- Group mapping runs on EVERY login: member of admin group ⇒ is_admin true,
  else false — but demotion is skipped (and logged) if it would leave zero
  active admins, mirroring `_guard_last_admin`.
- `GET /auth/methods` → `{"password": true, "oidc": {"enabled": bool, "name": str}}`
  (public) so the login page can show the SSO button.
- OIDC endpoints: `GET /auth/oidc/login` (redirect), `GET /auth/oidc/callback`
  (creates the same session cookie password login creates).

## Architecture invariants (DRY — these are hard rules)

1. ONE module, `backend/app/access/` (or similar), owns visibility:
   - `visible_vehicle_ids(db, user) -> set[str]` (admin ⇒ all)
   - `access_level(db, user, vehicle_id) -> "view" | "operate" | None`
   - FastAPI dependencies `ViewVehicle` / `OperateVehicle` for `{vehicle_id}`
     routes: resolve the vehicle once, 404 when not visible (NOT 403 — do not
     reveal existence), 403 when visible but the level is insufficient.
   - `RequireAdmin` dependency for admin routes.
2. NO route or service may compare user ids to decide visibility. Every current
   `owner_id ==` filter (28 sites across: dashboards/routes.py [keep — personal],
   vehicles/services.py, hooks/*, vehicle_profiles/services.py, secrets/routes.py,
   telemetry/services.py, devices/routes.py, api/events.py via list_vehicles)
   must be routed through the access module or deleted with the feature that
   needed it.
3. The SSE stream (api/events.py) already recomputes `list_vehicles` per push —
   after the sweep it must emit only visible vehicles per subscriber.
4. Permission strings live as constants in one place.

## The four-persona test (write it FIRST)

`backend/tests/test_access_model.py`: seed two vehicles V1, V2 and four users —
admin, operator (operate on V1), viewer (view on V1), stranger (no grants).
Walk EVERY endpoint (list + detail + mutation) and assert:

- lists contain exactly the visible set (stranger: empty; viewer/operator: V1),
- V2 detail/history/telemetry → 404 for all three non-admins,
- operate-mutations on V1 → 200/204 for operator+admin, 403 for viewer, 404 stranger,
- vehicle create/delete, hooks, secrets, grants, template, clear-all → admin only,
- profile create → 403 without `profiles.create`; editor can PUT/DELETE own
  profile only; deleting an assigned profile unassigns silently (assert the
  vehicle's profile is NULL afterwards and the response body carries no counts),
- device-side endpoints (enroll/config/telemetry batch) still work with device
  credentials, unaffected by user grants.

Also update every existing test that assumed ownership. `registered` fixture
users are not admins by default any more unless the fixture makes them one —
check `conftest.py` and keep the bootstrap-admin path working (first user is
still the bootstrap admin).

## Sequencing note

The frontend consumes: `access` on VehicleResponse, `editable` on profiles,
`/auth/methods`, `/vehicles/{id}/access`, `/admin/default-access`,
`can_create_profiles` in the users payload and permissions map. Keep these
shapes exactly as written here — the frontend work is built against this file.

## Style

Match the repo: comments explain WHY, not what; no dead code left behind;
`ruff format`, `ruff check`, `mypy backend/app` and `pytest backend` must pass.
Do not touch `frontend/` or `agent/` (Go) in the backend stage.
