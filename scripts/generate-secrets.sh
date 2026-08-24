#!/bin/sh
set -eu

python3 - <<'PY'
import base64
import secrets

print("VEHINODE_SESSION_PEPPER=" + secrets.token_urlsafe(48))
print("VEHINODE_MASTER_KEY=" + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
print("POSTGRES_PASSWORD=" + secrets.token_urlsafe(32))
PY
