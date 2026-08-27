#!/bin/sh
set -eu

role=${1:-app}
if [ "$#" -gt 0 ]; then
  shift
fi

case "$role" in
  app)
    alembic upgrade head
    set -- python -m uvicorn backend.app.main:app \
      --host 0.0.0.0 \
      --port 8000 \
      --proxy-headers \
      --forwarded-allow-ips="${CARHIBOU_FORWARDED_ALLOW_IPS:-*}" \
      "$@"
    ;;
  worker)
    set -- python -m backend.app.worker "$@"
    ;;
  *)
    set -- "$role" "$@"
    ;;
esac

exec "$@"
