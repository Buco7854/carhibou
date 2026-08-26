# Vehicle profiles

Profiles map vehicle-specific CAN frames to canonical metric names. YAML definitions
support unsigned/signed 8/16/32-bit integers, explicit byte slices, booleans, masks,
shifts, endianness, scale/offset, enums and sanity bounds. Safe computed multiplication
supports power from voltage/current. No profile expression uses Python `eval`.

A profile is a mapping and nothing more. Each signal carries its canonical name, the
label the interface shows for it, its unit, its source, its decoder and optional sanity
bounds. Evidence statuses, source URLs, per-signal prose and a vehicle family were all
carried here once and read by nothing. The hardware validation ledger, not the profile,
records which formulas have been confirmed against a physical vehicle.

Built-in profiles are YAML under `agent/profiles`; adding one requires synthetic fixtures
for each formula, source/license notes and an update to the hardware validation ledger.
Owners manage owner-scoped definitions on the dedicated **Telemetry profiles** page.
That page keeps bundled and custom profiles visible as persistent cards. Creating or
editing a profile opens a focused profile modal, while adding or editing one signal uses
a distinct signal modal; page or modal content is never repurposed as an implicit next
step. Those definitions are validated with the same Pydantic and agent decoder contracts, stored in PostgreSQL,
and embedded in versioned device configuration. What is embedded is a projection: a
tracker decodes frames rather than rendering a profile, so it receives the identifier,
the signal names, sources, decoders, units and bounds, and nothing else. Names,
descriptions and display names stay server-side, which halves the configuration a
tracker downloads. The agent validates the embedded ID and decoder structure before
atomically replacing last-known-good configuration.

Editing or deleting an assigned custom profile increments each affected device's config
version. Deletion also clears the vehicle assignment. Built-in definitions are read-only,
and another owner can neither list nor assign a custom definition. The frontend consumes
canonical metric names after decoding; dashboards never persist raw CAN identifiers.

A computed metric multiplies two decoded signals and may declare a `scale` that converts
the product into its stated unit. The bundled C-Zero definition multiplies pack voltage by
pack current and scales by `0.001`, so it publishes kilowatts rather than watts: every
VehiNode surface expects `battery.power` in kW, positive while the pack delivers energy and
negative while it absorbs it.
