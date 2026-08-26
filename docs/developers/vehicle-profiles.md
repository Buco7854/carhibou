# Vehicle profiles

Profiles map vehicle-specific CAN frames to canonical metric names. YAML definitions
support unsigned/signed 8/16/32-bit integers, explicit byte slices, booleans, masks,
shifts, endianness, scale/offset, enums and sanity bounds. Safe computed multiplication
supports power from voltage/current. No profile expression uses Python `eval`.

Each signal documents its name, display metadata, unit, source, decoder and optional
sanity bounds. Packaged profiles may also carry internal validation metadata and source
notes so physical claims remain aligned with the hardware ledger. This metadata is not
a user-facing "proof level" and is not requested when an owner creates a profile.

Built-in profiles are YAML under `agent/profiles`; adding one requires synthetic fixtures
for each formula, source/license notes and an update to the hardware validation ledger.
Owners manage owner-scoped definitions on the dedicated **Telemetry profiles** page.
That page keeps bundled and custom profiles visible as persistent cards. Creating or
editing a profile opens a focused profile modal, while adding or editing one signal uses
a distinct signal modal; page or modal content is never repurposed as an implicit next
step. Those definitions are validated with the same Pydantic and agent decoder contracts, stored in PostgreSQL,
and embedded in versioned device configuration. The agent validates the embedded ID and
decoder structure before atomically replacing last-known-good configuration.

Editing or deleting an assigned custom profile increments each affected device's config
version. Deletion also clears the vehicle assignment. Built-in definitions are read-only,
and another owner can neither list nor assign a custom definition. The frontend consumes
canonical metric names after decoding; dashboards never persist raw CAN identifiers.

A computed metric multiplies two decoded signals and may declare a `scale` that converts
the product into its stated unit. The bundled C-Zero definition multiplies pack voltage by
pack current and scales by `0.001`, so it publishes kilowatts rather than watts: every
VehiNode surface expects `battery.power` in kW, positive while the pack delivers energy and
negative while it absorbs it.
