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

## The names VehiNode knows

Every surface — dashboards, history, hooks, the agent's own decisions — is written
against canonical metric names, never against a vehicle's raw frames. A profile's
whole job is to translate one into the other, which is why a vehicle nobody has
seen before is a profile rather than a change to any of them.

Three names the agent reasons about, all boolean:

| Name | Meaning |
| --- | --- |
| `vehicle.ready` | The vehicle is switched on: ignition on, or an electric vehicle showing READY. A stated `false` outranks every other source. |
| `charging.active` | The vehicle is charging, which counts as in use. |
| `vehicle.state` | Display only. Its values are the vehicle's own words and nothing reasons about them. |

An enum may map a raw value straight to a boolean, so a profile says "on this
vehicle, four means ready" and the agent recognises no vehicle-specific vocabulary
at all. A value the profile does not map decodes to no reading, so a state nobody
described leaves the vehicle to be judged by motion instead of by a claim nobody
made.

Everything else is a reading: `battery.soc`, `battery.power`, `vehicle.speed`,
`engine.rpm` and so on. A name outside the set the interface knows still records
and still charts; it shows as its raw name rather than a translated one.

**A vehicle with no profile is not silent.** It records position and agent
health, and, where the vehicle answers standard diagnostic requests, the ten
readings those carry: `vehicle.speed`, `engine.rpm`, `engine.load`,
`engine.throttle`, `engine.coolant_temperature`, `engine.intake_temperature`,
`engine.maf`, `fuel.level`, `battery.soc` and `device.input_voltage`. Many
electric vehicles answer none of them, which is what a profile is for.

Monitoring applies the profile's identifiers as adapter pass filters before it
starts. Without them the adapter forwards the whole bus, which is several times what
the serial link can carry, and the frames the profile wanted arrive truncated.

Built-in profiles are YAML under `agent/profiles`; adding one requires synthetic fixtures
for each formula, source/license notes and an update to the hardware validation ledger.
Owners manage owner-scoped definitions on the dedicated **Telemetry profiles** page.
That page keeps bundled and custom profiles visible as persistent cards. Creating or
editing a profile opens a focused profile modal, while adding or editing one signal uses
a distinct signal modal; page or modal content is never repurposed as an implicit next
step. Those definitions are validated with the same Pydantic and agent decoder contracts, stored in PostgreSQL,
and embedded in versioned device configuration. What is embedded is a projection: a
agent decodes frames rather than rendering a profile, so it receives the identifier,
the signal names, sources, decoders, units and bounds, and nothing else. Names,
descriptions and display names stay server-side, which halves the configuration a
agent downloads. The agent validates the embedded ID and decoder structure before
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
