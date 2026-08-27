# Vehicle profiles

Profiles translate vehicle-specific CAN frames into canonical metrics. Every consumer,
including agent activity logic, history, dashboards and hooks, uses names such as `battery.soc`
rather than raw frame identifiers. An unfamiliar vehicle therefore needs a profile, not
vehicle-specific behavior in each surface.

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

A vehicle without a profile still records position and health. Where supported, standard
diagnostics can report speed, RPM, load, throttle, temperatures, MAF, fuel level, hybrid
battery remaining life and input voltage. Many EVs answer none of those requests.

## Filtering and configuration

Before continuous monitoring, the agent applies pass filters for the profile's CAN IDs.
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
