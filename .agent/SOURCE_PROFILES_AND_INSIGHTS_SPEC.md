# Source profiles and driving insights

Three connected changes: profiles move from vehicles to data sources and gain a second
type (mapping), a query-time segments API derives drives and charges from history, and
the dashboard gains five composable insight widgets. No named locations, no reverse
geocoding, no stored sessions.

## 1. Profiles belong to data sources

- The `vehicles.vehicle_profile` column moves to `agents.vehicle_profile` (squashed
  initial migration, project convention; no compatibility aliases). Agent enrollment
  gains an optional profile choice; the agent settings modal allows changing it. The
  vehicle create/edit form loses its profile field and hint. Config delivery keeps its
  shape but sources the profile from the agent row; profile edits bump config_version
  for agents that reference the profile (not vehicles).
- The enrollment cadence estimate takes its signal count from the chosen profile in
  the form instead of the vehicle.
- Profiles gain a `type`: `can` (existing definitions, unchanged schema) and `mapping`
  (new). The profiles API and page expose both; type is chosen at creation and fixed.

## 2. Mapping profiles

A mapping profile converts a connector's raw key/value stream into our metric format:

```
definition: {
  id, name, version, description,
  type: "mapping",
  passthrough_prefix: "teslamate",       # unmatched keys land under this prefix; "" disables passthrough
  ignore: ["latitude", "longitude", ...] # keys dropped entirely
  rules: [
    { match: "battery_level", target: "battery.soc" },
    { match: "elevation", target: "position.altitude" },
    { match: "charging_state", target: "charging.active",
      transform: { enum: { "Charging": true, "charging": true, "*": false } } },
    { match: "charge_energy_added", target: "charging.energy_added",
      transform: { scale: 1, offset: 0 } },
    { match: "power", target: "battery.power", transform: { scale: 1, offset: 0 } },
    ...
  ]
}
```

- `target` is a metric key, a
  `position.<latitude|longitude|altitude|speed|heading|accuracy>` field, or `position`
  with a `json` transform for a position object.
- Transforms: `scale`, `offset`, `enum` (string → value, `"*"` default), `boolean`
  (truthy strings), and `json` pass-one-level-flatten. Validation fails closed on
  unknown fields, duplicate matches, and invalid targets; coercion at runtime stays
  per-value fail-open exactly as the connector runtime does today.
- The current hard-coded TeslaMate mapping is re-expressed as a bundled mapping
  profile (`teslamate-mqtt-v1`), living beside the bundled CAN profile YAMLs and
  validated by the same round-trip mechanism (a shared Python mapping engine applies
  profiles; the connector runtime uses that engine).
- Connectors reference a mapping profile (`connectors.mapping_profile`, default the
  bundled TeslaMate profile for kind teslamate.mqtt). The connector form gains the
  selector; changing it bumps config_version.
- Custom mapping profiles are created and edited on the existing Profiles page:
  the editor for type mapping is a rule list (match, target, transform fields) in the
  established editor idiom; bundled profiles stay read-only with a clone path the
  same way custom CAN profiles are created today.

### Contract resolutions (binding; the frontend is already built against these)

- The profile API keeps its established flat body shape: create/update send
  `{name, description, type, ...definition fields}` with `type` `"can"` or
  `"mapping"` (mapping sends `passthrough_prefix`, `ignore`, `rules`), not a nested
  `definition` object.
- `boolean` and `json` transforms are flags: `{boolean: true}`, `{json: true}`.
- `mapping_profile` travels top-level in connector create/update beside `kind` and
  `name`, not inside `config` (whose keys stay fail-closed).
- The server enforces type fit: agents accept only `can` profiles, connectors only
  `mapping` profiles.
- Deleting a profile clears agent references to it and resets connectors that used it
  to their kind's bundled default, bumping config_version for both.
- Segments carry no server id; clients key selection by `{kind, start}`.
- The bundled TeslaMate location rule accepts every supported position field from the JSON
  object, including speed and heading. An object with none of those fields emits no
  telemetry value and records a mapping note.

## 3. Segments API (query-time, nothing stored)

`GET /vehicles/{id}/segments?start=...&end=...` (view access), computed on read from
telemetry using canonical metrics only, so it works for any source:

- Drive detection evidence, in precedence order: `vehicle.in_use` boolean; `vehicle.state`
  equal to driving-like values; position speed above 1 km/h; charging false plus
  movement between consecutive positions. Contiguous drive evidence with gaps under
  180 seconds joins into one drive; drives shorter than 60 seconds are dropped.
- Charge detection: `charging.active` true, else `charging.power` > 0. Same join rule.
  Charges shorter than 60 seconds are dropped.
- Response:

```
{ "drives": [ { start, end, duration_seconds, start_position?, end_position?,
                distance_km?, avg_speed?, max_speed?, soc_start?, soc_end?,
                energy_kwh? } ],
  "charges": [ { start, end, duration_seconds, position?, soc_start?, soc_end?,
                 energy_kwh?, peak_power?, avg_power? } ] }
```

- `distance_km` prefers odometer delta, falls back to summed GPS haversine;
  `energy_kwh` for drives is battery-energy delta when capacity and soc exist, for
  charges prefers canonical `charging.energy_added` delta, falls back to integrating
  `charging.power` over time. Every field is optional and omitted when the underlying
  metrics are absent; missing data never errors.
- Range is start-inclusive and end-exclusive, and capped (start required, span <= 92
  days). Downsampling-safe: computed from raw rows via the entries query machinery, not
  the downsampled history endpoint.
- Segment detail (charts) needs no new endpoint: clients call the existing history
  API with the segment's start/end.

## 4. Insight widgets (five, composing like existing ones)

All are standard registry widgets: `isEmpty` predicates, `hide_when_empty` opt-in,
grid/pinned-vehicle behavior, phone stacking, both locales.

- Selection precedent: the existing vehicle-selector pattern extends one level down.
  The activity feed exposes the selected segment to the dashboard the way the vehicle
  selector exposes the selected vehicle; follower widgets use it when present, else
  their own default (most recent segment in range). A follower widget whose range does
  not contain the selected `{kind, start}` shows an explicit not-in-range empty state
  instead of silently falling back.
- `route-map`: trail for a time range with per-point speed coloring (existing map
  stack), follows the selected drive; tapping two points on the trail shows the A-to-B
  readout (distance, time, soc delta, energy when derivable). Replaces `position-map`
  in the Overview preset (preset version bump); `position-map` remains available.
- `activity-feed`: merged drives and charges newest-first for the range, type filter,
  acts as segment selector.
- `segment-stats`: stat grid for the selected segment (drive: distance, duration,
  avg/max speed, energy; charge: energy added, duration, soc span, peak power).
- `charge-curve`: power vs state-of-charge chart for the selected or latest charge in
  range, with peak/average annotations, via the existing chart stack.
- `period-stats`: distance, drive count, energy charged, efficiency (energy/distance)
  for a chosen period with delta vs the previous equal period.
- Time ranges reuse the existing widget range idiom (day/week/month) where present.

## Verification

- Backend: mapping-engine unit tests (every transform, fail-closed validation,
  fail-open runtime coercion, TeslaMate bundled profile equivalence against the
  current mapping's expected outputs for all 78 topics); segments tests over synthetic
  histories (gap joining, minimum duration, missing-metric omission, precedence,
  boundary conditions, capped range); profile-move tests (enrollment with profile,
  config delivery, config_version bumps, vehicle API no longer accepts a profile);
  access tests for the segments endpoint.
- Frontend: profile pickers (enrollment, agent settings, connector form), mapping
  editor create/edit/clone, each widget's empty/populated/selection states, feed
  selection driving followers, Overview preset swap, locale parity.
- Full repo gate including browser e2e against Postgres where CI runs it.

## Documentation

Existing pages only, no em dashes, never "self-hosted": profiles page docs explain the
two types; data-sources guide gains profile selection; architecture gains the mapping
engine and segments derivation.
