# ADR 0007: Standalone Go vehicle agent

## Status

Accepted.

## Decision

Build the vehicle-side agent from one Go codebase with CGO disabled. Publish separate
Linux executables for ARMv6, ARMv7, ARM64 and AMD64. A small POSIX bootstrap detects the
CPU, verifies the selected artifact with SHA-256, installs it, and delegates enrollment,
systemd lifecycle, updates and complete removal to the executable.

Compile the SQLite offline outbox and serial support into the executable. Keep server
profiles declarative and send their validated JSON definitions in device configuration.
Persist an explicit insecure-HTTP opt-in with development credentials; HTTPS remains the
default requirement.

## Consequences

- Agents do not need Python, a virtual environment, compiler toolchain or package-manager
  update.
- One physical binary cannot span CPU instruction sets, so releases contain four artifacts
  built from identical source and the bootstrap chooses one.
- The local SQLite file is not a service. It remains the crash-safe outbox that retains
  samples through power and network loss until the server acknowledges their IDs.
- Linux systems can run the executable directly; automatic account and service management
  requires systemd and standard account-management tools.
- Cross-build and fixture success are not physical hardware validation.
