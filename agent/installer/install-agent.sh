#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
  echo "Installer must run as root (use sudo)" >&2
  exit 1
fi

VERSION="0.1.0"
SERVER=""
TOKEN=""
UPDATE_ONLY="false"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --server) SERVER="$2"; shift 2 ;;
    --token) TOKEN="$2"; shift 2 ;;
    --version) VERSION="$2"; shift 2 ;;
    --update-only) UPDATE_ONLY="true"; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$SERVER" ]; then
  echo "--server is required" >&2
  exit 2
fi
if [ "$UPDATE_ONLY" = "false" ] && [ -z "$TOKEN" ]; then
  echo "--token is required for initial enrollment" >&2
  exit 2
fi
case "$SERVER" in
  https://*|http://localhost|http://localhost:*|http://127.0.0.1|http://127.0.0.1:*) ;;
  *) echo "Server must use HTTPS (except localhost)" >&2; exit 2 ;;
esac

if [ ! -r /etc/os-release ]; then
  echo "Unsupported OS: /etc/os-release is missing" >&2
  exit 1
fi
. /etc/os-release
case "${ID:-}:${ID_LIKE:-}" in
  *debian*|raspbian:*) ;;
  *) echo "VehiNode supports Raspberry Pi OS and Debian" >&2; exit 1 ;;
esac

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl python3 python3-venv

if ! id vehinode-agent >/dev/null 2>&1; then
  useradd --system --home /var/lib/vehinode-agent --shell /usr/sbin/nologin vehinode-agent
fi
install -d -o root -g root -m 0755 /opt/vehinode-agent
install -d -o vehinode-agent -g vehinode-agent -m 0750 /var/lib/vehinode-agent
install -d -o vehinode-agent -g vehinode-agent -m 0750 /etc/vehinode-agent

ARTIFACT="vehinode-${VERSION}-py3-none-any.whl"
BASE="${SERVER%/}/agent/releases/${VERSION}"
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT INT TERM
case "$SERVER" in
  https://*)
    curl -fL --proto '=https' --tlsv1.2 "${BASE}/${ARTIFACT}" -o "${TMPDIR}/${ARTIFACT}"
    curl -fL --proto '=https' --tlsv1.2 "${BASE}/${ARTIFACT}.sha256" -o "${TMPDIR}/${ARTIFACT}.sha256"
    ;;
  *)
    curl -fL "${BASE}/${ARTIFACT}" -o "${TMPDIR}/${ARTIFACT}"
    curl -fL "${BASE}/${ARTIFACT}.sha256" -o "${TMPDIR}/${ARTIFACT}.sha256"
    ;;
esac
(cd "$TMPDIR" && sha256sum -c "${ARTIFACT}.sha256")

if [ ! -x /opt/vehinode-agent/venv/bin/python ]; then
  python3 -m venv /opt/vehinode-agent/venv
fi
/opt/vehinode-agent/venv/bin/pip install --no-cache-dir --upgrade "${TMPDIR}/${ARTIFACT}"

if [ "$UPDATE_ONLY" = "false" ]; then
  runuser -u vehinode-agent -- /opt/vehinode-agent/venv/bin/vehinode-agent \
    --config-dir /etc/vehinode-agent --data-dir /var/lib/vehinode-agent \
    enroll --server "$SERVER" --token "$TOKEN"
fi

install -m 0644 /dev/stdin /etc/systemd/system/vehinode-agent.service <<'UNIT'
[Unit]
Description=VehiNode vehicle telemetry agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=vehinode-agent
Group=vehinode-agent
ExecStart=/opt/vehinode-agent/venv/bin/vehinode-agent --config-dir /etc/vehinode-agent --data-dir /var/lib/vehinode-agent run
Restart=always
RestartSec=10
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/vehinode-agent /etc/vehinode-agent

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now vehinode-agent
ln -sf /opt/vehinode-agent/venv/bin/vehinode-agent /usr/local/bin/vehinode-agent
systemctl --no-pager --full status vehinode-agent || true
/opt/vehinode-agent/venv/bin/vehinode-agent --config-dir /etc/vehinode-agent --data-dir /var/lib/vehinode-agent doctor || true
echo "VehiNode agent ${VERSION} installed. Run: vehinode-agent status"
