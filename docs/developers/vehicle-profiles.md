# Vehicle profiles

Profiles translate source-specific data into canonical metrics. Every consumer, including
agent activity logic, history, dashboards and hooks, uses names such as `battery.soc`
rather than source-specific identifiers. Profiles are instance-wide and have one fixed type:

- `can` decodes vehicle CAN frames in an enrolled agent.
- `mapping` converts an external connector stream into metrics and position fields.

The type is chosen when a custom profile is created and cannot be changed later. Built-in
profiles are read-only and can be cloned into editable custom profiles.

## CAN profiles

YAML definitions support signed and unsigned 8/16/32-bit integers, byte slices, booleans,
masks, shifts, endianness, scale and offset, enums and sanity bounds. A safe computed
multiplication supports values such as voltage × current. No expression uses `eval`.

| Canonical name | Meaning |
| --- | --- |
| `vehicle.ready` | Authoritative switched-on or READY state; explicit false outranks other evidence |
| `charging.active` | Charging state, which the agent treats as in use |
| `vehicle.state` | Display-only vocabulary; activity logic does not interpret it |

An unmapped enum value produces no reading, so unknown state falls back to motion or bus
evidence. Other canonical names are readings. Names unknown to the interface are still
recorded and charted under their raw canonical name.

An agent without a CAN profile still records position and health. Where supported, standard
diagnostics can report speed, RPM, load, throttle, temperatures, MAF, fuel level, hybrid
battery remaining life and input voltage. Many EVs answer none of those requests.

## Filtering and configuration

Before continuous monitoring, the agent applies pass filters for the selected profile's CAN
IDs.
Without them a busy vehicle bus can exceed the serial link and truncate the frames the
profile needs.

Built-in profiles live under `agent/profiles`. Adding one requires fixture coverage for
every formula, source and license notes, and a hardware-ledger update. Evidence belongs
in that ledger, not in downloaded profile configuration.

Owners with the profile-creation allowance manage custom instance-wide definitions in
**Telemetry profiles**. The same validation contract stores them in PostgreSQL and
projects only decoder data into versioned agent configuration. Display names and prose
remain server-side. The agent validates the embedded ID and decoder structure before
atomically replacing last-known-good configuration.

Editing or deleting an assigned custom profile increments affected agent configuration;
deletion also unassigns it. Built-ins are read-only. A creator may manage their own
custom definitions, while administrators may manage all of them.

Computed units must match the canonical contract. For example, the C-Zero profile scales
voltage × current by `0.001` to publish `battery.power` in kW, positive while delivering
energy and negative while absorbing it.

## Mapping profiles

A mapping profile declares an optional passthrough prefix, ignored source keys and ordered
rules. Each rule has one unique `match`, a canonical metric or position `target`, and an
optional transform. Supported transforms are numeric scale and offset, an enum with an
optional `*` default, truthy-string boolean conversion, and one-level JSON flattening.
A JSON position object targets `position`; individual numeric values target
`position.latitude`, `position.longitude`, `position.altitude`, `position.speed`,
`position.heading` or `position.accuracy`.

Unknown profile fields, duplicate matches, invalid targets and incompatible transforms fail
validation. At runtime, one malformed source value is omitted and recorded as a mapping
error without discarding other values in the same connector window. Unmatched values use
the configured passthrough prefix, or are omitted when the prefix is empty.

The bundled `teslamate-mqtt-v1` mapping translates TeslaMate MQTT topics into canonical
Carhibou keys, position fields and `teslamate.*` passthrough metrics. Mapping profiles use
the same create, edit, clone and delete flow as CAN profiles. Editing one increments the
configuration version of every connector that references it. Deleting one resets those
connectors to the bundled mapping for their connector kind.
