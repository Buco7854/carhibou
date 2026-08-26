# Vehicles

Vehicles belong to a user independently of the login provider. An administrator adds
people from **Settings → People**; self-registration closes after the first account. Creation asks only for a
name and, optionally, a telemetry profile. Creating vehicles is an administrator action; see [Who sees what](./access.md). It does not ask anyone to classify the
powertrain or enter specifications that are unrelated to collecting telemetry. Raw
C-Zero fields never enter the generic table; choose a profile only when it matches the
vehicle and capture hardware.

## Telemetry profiles

A vehicle profile is a declarative decoding map from raw CAN frames and bytes to named
metrics such as `battery.soc`. VehiNode ships reviewed built-in definitions and lets each
accounts with the profile-creation allowance create profiles on the dedicated **Telemetry profiles** page. Profiles are instance-wide and
can be assigned directly from a vehicle card. Saving, changing or deleting a profile
increments the assigned agent configuration; the server then sends the complete,
validated definition to the agent as last-known-good configuration.

Only enter CAN identifiers and formulas backed by evidence you trust. VehiNode validates
the structure but cannot prove that a reverse-engineered formula matches a physical car,
and it never invents one.

Live state shows the latest position, canonical metrics and device health. Online state
uses reporting freshness rather than assuming every parked vehicle reports rapidly.

Each card pairs the vehicle image with live readings and direct history/agent actions.
It never labels a vehicle electric, combustion or hybrid.

A card leads with an energy level, `battery.soc` or then `fuel.level`, when one is
reported. Neither is guaranteed: no OBD-II PID exposes traction-battery charge, and the
standard fuel-level PID is frequently unimplemented. So when no energy level exists the
card promotes the most conventional reading the vehicle does send, and a vehicle that has
reported nothing says so. VehiNode never turns a missing reading into `0%`, and no surface
offers a reading the vehicle has not reported.

Charging appears once it is known, with its rate when available, and the level bar turns
green while the pack is taking charge. Search is local and immediate; the All, Online and
Parked filters only change the visible catalog and do not alter reporting configuration.

## Vehicle photos

Use **Add photo** on a vehicle to upload a JPEG, PNG or WebP image up to 25 MiB. You can
replace or remove it from the same media frame. Adding a photo does not change the card
dimensions. Until then, VehiNode shows a plain
missing-image icon directly in the empty photo area, without placeholder copy or a
substitute vehicle illustration.

Photos are visible to everyone who can see the vehicle. VehiNode stores the image as a file in its
media directory; PostgreSQL contains only its content type, size, fingerprint and
storage key. Docker installations persist these files in the `vehicle-media` volume,
which must be backed up together with PostgreSQL.

## Vehicle deletion

Delete a vehicle from its garage card. The confirmation explains that deletion is
permanent: telemetry history, current state, agents and credentials, pending enrollment
tokens, the photo, and vehicle-specific hooks are removed together. Dashboard widgets
that were pinned to the deleted vehicle are retained and return to following the
dashboard vehicle selector.
