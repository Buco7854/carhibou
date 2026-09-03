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
"$PYTHON" -m pytest -m "not postgres" backend/tests agent/tests
CARHIBOU_DATABASE_URL=sqlite:////tmp/carhibou-migration-check.sqlite3 "$PYTHON" -m alembic upgrade head
CARHIBOU_DATABASE_URL=sqlite:////tmp/carhibou-migration-check.sqlite3 "$PYTHON" -m alembic check
CARHIBOU_DATABASE_URL=sqlite:////tmp/carhibou-migration-check.sqlite3 "$PYTHON" -m alembic downgrade base
# Setuptools otherwise reuses build/lib and can put deleted migration modules
# into a later wheel. A release check must prove the current tree, not leftovers.
rm -rf -- build
"$PYTHON" -m build --wheel --no-isolation

(cd agent && test -z "$(gofmt -l cmd internal)" && go vet ./... && go test ./...)

(cd frontend && npm run lint && npm run typecheck && npm test && npm run build)
(cd docs && npm run docs:build)
