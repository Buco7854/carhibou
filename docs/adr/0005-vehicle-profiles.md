# ADR 0005: Declarative vehicle profiles

Status: accepted (2026-08-23)

## Decision

Manufacturer signals are YAML profiles decoded by a small allowlisted operation set:
integer/slice/bit extraction, endianness, scale, offset, booleans, enums and bounds.
There is no `eval`. Output uses canonical metric names and evidence status.

## Consequences

The frontend is vehicle-agnostic. Unknown reverse-engineered formulas remain marked
experimental or unknown and physical validation is recorded separately.
