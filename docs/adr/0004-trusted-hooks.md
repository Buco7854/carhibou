# ADR 0004: Trusted Python hooks with process containment

Status: accepted (2026-08-23)

## Decision

Python hooks are privileged code. Telemetry transactions enqueue generic events and
PostgreSQL jobs; a separate worker starts a fresh child process per execution with a
timeout, output cap and OS limits where available. State and execution results are
committed by the worker. Hooks execute once by default; failures require manual retry.

## Consequences

Broken hooks cannot fail ingestion. Process limits are reliability containment, not a
sandbox against hostile administrators. Users with `hooks.manage_code` have privileged
code execution in the hook environment.
