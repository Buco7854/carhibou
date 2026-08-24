# Definition of Done

The detailed implementation checklist is maintained in `.agent/PLAN.md`. Completion
requires a fresh locked install, migrations, Python/static analysis and tests, Go agent
format/vet/tests/cross-builds, frontend tests/build, documentation build, PostgreSQL integration/e2e, Docker build and Compose
smoke test.

Physical hardware items are separately tracked in the
[hardware validation ledger](../agent/hardware-validation.md). A software integration
can be complete while physical validation remains pending, but VehiNode never describes
fixture/simulator results as physical proof.
