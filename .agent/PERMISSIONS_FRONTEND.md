# Frontend brief — permission-aware UI

Read `.agent/PERMISSIONS_SPEC.md` first for the model. This file adds the UI
decisions. The backend is already implemented; trust the shapes in the spec's
"Sequencing note" and read the actual backend code when in doubt. If you find a
contract mismatch, report it — do not hack around it in the frontend.

## Gating rules

The server is the enforcement point; the frontend's job is to not show doors
that are locked. Every gate below hides the control entirely (no disabled
buttons explaining themselves — absence is the design language here).

- `auth.user.permissions['system.admin']` — admin.
- `auth.user.permissions['profiles.create']` — may create profiles.
- `vehicle.access` (`"view" | "operate"`) — per-vehicle level from the API.

### Vehicles page
- "Add vehicle" and vehicle deletion: admin only.
- Per card, operate-only: the profile select (viewers see the profile name as
  plain text, or nothing when unset), "Clear data", photo add/change/remove.

### Data sources page (agents)
- The enrollment form's vehicle select lists only vehicles with
  `access === 'operate'`; "Add agent" hidden when that list is empty.
- Per row, operate-only (look the vehicle up by `agent.vehicle_id`):
  Settings, rotate, revoke, delete.

### Hooks
- Admin only: the nav entry and the route (router guard like `/admin`).

### Profiles page
- "New profile" gated on `profiles.create` or admin.
- Edit/delete per profile gated on the new `profile.editable` flag from the
  API. Built-ins remain read-only regardless.

### Admin page (extend `AdminView.vue`)
- People: add a "can create profiles" toggle per user
  (`PATCH /users/{id}` with `can_create_profiles`).
- New "Vehicle access" section: pick a vehicle, see its grants
  (`GET /vehicles/{id}/access` → `[{user_id, email, display_name, level}]`),
  add/remove users and switch view/operate, save as full replacement
  (`PUT /vehicles/{id}/access` with `[{user_id, level}]`).
- New "Default access" section: what a NEW user receives —
  `profiles_create` checkbox plus a grants list (vehicle + level), via
  `GET/PUT /admin/default-access`. Make the copied-not-live semantics visible
  in the hint text: editing this affects only users created afterwards.

### Login
- `GET /auth/methods` (public). When `oidc.enabled`, show a "Continue with
  {name}" button above the password form → `window.location.href =
  '/api/v1/auth/oidc/login'`. Password form stays.

## Mechanics

- Update `frontend/src/api/types.ts`: `Vehicle.access`, `VehicleProfile.editable`
  (on the response wrapper, wherever the backend put it), `UserAccount.
  can_create_profiles`, an `AuthMethods` type.
- i18n: en AND fr for every new string. French must be native quality — watch
  elision ("l'agent", "l'accès"), and reuse the existing tone.
- Where several views need the same gate, put the helper in one place
  (`vehicleDisplay.ts` already exports per-vehicle helpers; follow that pattern)
  — no copy-pasted permission expressions across views.

## Tests

- Update existing tests that assume every user can do everything (the mounted
  fixtures now need `access` on vehicle objects and a permissions map on the
  auth user — check how tests stub `auth`).
- New coverage, minimum: a viewer's vehicle card shows no operate controls; an
  operator's does; profiles page hides create without the permission and hides
  edit/delete when `editable` is false; login shows the SSO button only when
  methods says enabled; admin grants section does a full-replacement PUT.
- e2e `frontend/e2e/core-flow.spec.ts` must still pass — the bootstrap user is
  an admin, so the flow keeps its rights; fix selectors if layout shifted.

## Verify before reporting

`cd frontend && npm run lint && npx vue-tsc --noEmit && npm test`, then from the
repo root `./scripts/check.sh`, then the playwright e2e. All green. Do not
commit or push — the orchestrator reviews and commits. Report files changed,
new i18n keys, and any backend contract mismatches found.
