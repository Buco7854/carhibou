#!/bin/sh
set -eu

if [ -x .venv/bin/python ]; then
  PYTHON=.venv/bin/python
  RUFF=.venv/bin/ruff
  MYPY=.venv/bin/mypy
else
  PYTHON=python3
  RUFF=ruff
  MYPY=mypy
fi

"$RUFF" check backend agent
"$RUFF" format --check backend agent
"$MYPY" backend agent
"$PYTHON" -m pytest backend/tests agent/tests
VEHINODE_DATABASE_URL=sqlite:////tmp/vehinode-migration-check.sqlite3 "$PYTHON" -m alembic upgrade head
VEHINODE_DATABASE_URL=sqlite:////tmp/vehinode-migration-check.sqlite3 "$PYTHON" -m alembic check
VEHINODE_DATABASE_URL=sqlite:////tmp/vehinode-migration-check.sqlite3 "$PYTHON" -m alembic downgrade base
"$PYTHON" -m build --wheel --no-isolation

(cd frontend && npm run lint && npm run typecheck && npm test && npm run build)
(cd docs && npm run docs:build)
