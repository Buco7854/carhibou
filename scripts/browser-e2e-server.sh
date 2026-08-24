#!/bin/sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
E2E_RUNTIME=$(mktemp -d "${TMPDIR:-/tmp}/vehinode-browser-e2e.XXXXXX")
APP_PID=""
WORKER_PID=""

cleanup() {
  [ -z "$APP_PID" ] || kill "$APP_PID" 2>/dev/null || true
  [ -z "$WORKER_PID" ] || kill "$WORKER_PID" 2>/dev/null || true
  [ -z "$APP_PID" ] || wait "$APP_PID" 2>/dev/null || true
  [ -z "$WORKER_PID" ] || wait "$WORKER_PID" 2>/dev/null || true
  rm -rf "$E2E_RUNTIME"
}
trap cleanup EXIT HUP INT TERM

if [ -x "$PROJECT_ROOT/.venv/bin/python" ]; then
  PYTHON="$PROJECT_ROOT/.venv/bin/python"
else
  PYTHON=python3
fi

if [ -z "${VEHINODE_DATABASE_URL:-}" ]; then
  export VEHINODE_DATABASE_URL="sqlite:///$E2E_RUNTIME/vehinode.sqlite3"
fi
export VEHINODE_FRONTEND_DIR="$PROJECT_ROOT/frontend/dist"
export VEHINODE_PUBLIC_URL="http://127.0.0.1:18124"
export VEHINODE_WORKER_ID="browser-e2e-worker"
export VEHINODE_LOG_LEVEL="WARNING"

cd "$PROJECT_ROOT"
"$PYTHON" -m alembic upgrade head
"$PYTHON" -m backend.app.worker &
WORKER_PID=$!
"$PYTHON" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 18124 &
APP_PID=$!
wait "$APP_PID"
