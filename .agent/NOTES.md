# Temporary engineering notes

- Local runner has Python 3.11.2 and Node 22.23.2, but no Docker/Podman or PostgreSQL
  client/server. SQLite covers the fast suite; the workflow must provide PostgreSQL and
  the container smoke run.
- Hardware validation needs physical SIM7600, OBDLink SX and C-Zero access. Do not turn
  any experimental C-Zero metric to verified based only on replay fixtures.
