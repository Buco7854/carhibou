#!/bin/sh
set -eu

if [ "$#" -eq 0 ]; then
  python3 - <<'PY'
import base64
import secrets

print("VEHINODE_SESSION_PEPPER=" + secrets.token_urlsafe(48))
print("VEHINODE_MASTER_KEY=" + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
print("POSTGRES_PASSWORD=" + secrets.token_urlsafe(32))
PY
  exit 0
fi

if [ "$#" -ne 2 ] || [ "$1" != "--write" ]; then
  echo "Usage: $0 [--write ENV_FILE]" >&2
  exit 2
fi

env_file=$2
if [ ! -f "$env_file" ]; then
  echo "Environment file not found: $env_file" >&2
  exit 1
fi

python3 - "$env_file" <<'PY'
import base64
import os
from pathlib import Path
import secrets
import sys

path = Path(sys.argv[1])
values = {
    "VEHINODE_SESSION_PEPPER": secrets.token_urlsafe(48),
    "VEHINODE_MASTER_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
    "POSTGRES_PASSWORD": secrets.token_urlsafe(32),
}

result: list[str] = []
written: set[str] = set()
for line in path.read_text(encoding="utf-8").splitlines():
    key = line.split("=", 1)[0].strip()
    if key in values and not line.lstrip().startswith("#"):
        result.append(f"{key}={values[key]}")
        written.add(key)
    else:
        result.append(line)

for key, value in values.items():
    if key not in written:
        result.append(f"{key}={value}")

path.write_text("\n".join(result) + "\n", encoding="utf-8")
os.chmod(path, 0o600)
PY

echo "Generated VehiNode secrets in $env_file (permissions set to 0600)."
