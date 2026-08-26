# ADR 0005: Declarative vehicle profiles

Status: accepted (2026-08-23)

## Decision

Manufacturer signals are YAML profiles decoded by a small allowlisted operation set:
integer/slice/bit extraction, endianness, scale, offset, booleans, enums and bounds.
There is no `eval`. Output uses canonical metric names.

## Consequences

The frontend is vehicle-agnostic. A profile holds the mapping and the label to show for
it; whether a reverse-engineered formula has been confirmed against a physical vehicle
belongs to the hardware validation ledger. Carrying provenance as profile data was
dropped: nothing read it, and it was over half of every configuration an agent
downloaded.
