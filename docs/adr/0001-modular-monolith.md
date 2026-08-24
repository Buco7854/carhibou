# ADR 0001: Modular monolith

Status: accepted (2026-08-23)

## Context

The expected deployment has 1–100 vehicles and should remain understandable and
operable for years without a distributed-systems platform.

## Decision

Use one FastAPI codebase with explicit domain modules, one Vue SPA, PostgreSQL, and a
worker built from the same image. PostgreSQL is both database and durable job queue.

## Alternatives

Microservices and broker-based queues were rejected as needless failure modes and
operational cost. A single-process worker was rejected because hooks need isolation.

## Consequences

Transactions can keep ingestion atomic. Modules must maintain explicit boundaries.
The app and worker scale independently without becoming separate products.
