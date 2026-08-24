# Vehicle profiles

Profiles map vehicle-specific CAN frames to canonical metric names. YAML definitions
support unsigned/signed 8/16/32-bit integers, explicit byte slices, booleans, masks,
shifts, endianness, scale/offset, enums and sanity bounds. Safe computed multiplication
supports power from voltage/current. No profile expression uses Python `eval`.

Each signal documents its name, display metadata, unit, source, decoder, evidence
status, references and notes. Status is one of `verified`, `experimental`, `unknown` or
`deprecated`. Community reverse-engineering begins as experimental.

To add a profile, add YAML under `agent/profiles`, synthetic fixtures for each formula,
source/license notes, and update the hardware validation ledger. The frontend consumes
canonical names, never raw CAN IDs.
