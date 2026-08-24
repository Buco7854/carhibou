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

Run the complete browser journey separately after installing Chromium once:

```bash
cd frontend
npx playwright install chromium
npm run test:e2e
```

Locally, the browser suite creates and removes its own temporary SQLite database and
runs both the API and background hook worker. Set `VEHINODE_DATABASE_URL` to exercise
another disposable database. CI runs the same journey against PostgreSQL. Failed runs
retain a Playwright trace, screenshot and video under `frontend/test-results/`.
