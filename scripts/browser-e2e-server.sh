#!/bin/sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
E2E_STATE="${TMPDIR:-/tmp}/carhibou-browser-e2e-pids"

# A trap cannot run when the runner kills this script outright, which is how a
# cancelled or timed-out run ends, so every start clears what the last one left.
# Without this a worker survived each such run along with its temporary directory,
# and a surviving worker competes with the live one for the same queue. The names
# come from a file this script wrote, so nothing else can be caught by it.
if [ -f "$E2E_STATE" ]; then
  while read -r stale; do
    [ -z "$stale" ] || kill "$stale" 2>/dev/null || true
  done < "$E2E_STATE"
  rm -f "$E2E_STATE"
fi
rm -rf "${TMPDIR:-/tmp}"/carhibou-browser-e2e.??????

E2E_RUNTIME=$(mktemp -d "${TMPDIR:-/tmp}/carhibou-browser-e2e.XXXXXX")
APP_PID=""
WORKER_PID=""

cleanup() {
  [ -z "$APP_PID" ] || kill "$APP_PID" 2>/dev/null || true
  [ -z "$WORKER_PID" ] || kill "$WORKER_PID" 2>/dev/null || true
  [ -z "$APP_PID" ] || wait "$APP_PID" 2>/dev/null || true
  [ -z "$WORKER_PID" ] || wait "$WORKER_PID" 2>/dev/null || true
  rm -rf "$E2E_RUNTIME"
  rm -f "$E2E_STATE"
}
trap cleanup EXIT HUP INT TERM

if [ -x "$PROJECT_ROOT/.venv/bin/python" ]; then
  PYTHON="$PROJECT_ROOT/.venv/bin/python"
else
  PYTHON=python3
fi

if [ -z "${CARHIBOU_DATABASE_URL:-}" ]; then
  export CARHIBOU_DATABASE_URL="sqlite:///$E2E_RUNTIME/carhibou.sqlite3"
fi
export CARHIBOU_FRONTEND_DIR="$PROJECT_ROOT/frontend/dist"
export CARHIBOU_MEDIA_DIR="$E2E_RUNTIME/media"
export CARHIBOU_PUBLIC_URL="http://127.0.0.1:18124"
export CARHIBOU_WORKER_ID="browser-e2e-worker"
export CARHIBOU_LOG_LEVEL="WARNING"
export CARHIBOU_BOOTSTRAP_ADMIN_EMAIL="browser-owner@example.com"
export CARHIBOU_BOOTSTRAP_ADMIN_PASSWORD="browser-e2e-password-2026"
export CARHIBOU_BOOTSTRAP_ADMIN_DISPLAY_NAME="Browser Owner"

cd "$PROJECT_ROOT"
"$PYTHON" -m alembic upgrade head
"$PYTHON" -m backend.app.worker &
WORKER_PID=$!
"$PYTHON" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 18124 &
APP_PID=$!
printf '%s\n%s\n' "$WORKER_PID" "$APP_PID" > "$E2E_STATE"
wait "$APP_PID"
