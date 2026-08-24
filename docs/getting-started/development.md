# Development

Use Python 3.13 and Node 22. Exact package versions and npm lockfiles are committed.

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
VEHINODE_DATABASE_URL=sqlite:///./dev.db .venv/bin/alembic upgrade head
cd frontend && npm ci && npm run dev
```

Run `./scripts/check.sh` before committing. Backend tests use SQLite for fast feedback;
CI additionally migrates and tests PostgreSQL. Follow `AGENTS.md` and keep `.agent/`
truth current.
