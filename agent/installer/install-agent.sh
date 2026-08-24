#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
  echo "Installer must run as root (use sudo)" >&2
  exit 1
fi

AGENT_VERSION="0.1.0"
SERVER=""
TOKEN=""
UPDATE_ONLY="false"
ALLOW_INSECURE_HTTP="false"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --server) SERVER="$2"; shift 2 ;;
    --token) TOKEN="$2"; shift 2 ;;
    --version) AGENT_VERSION="$2"; shift 2 ;;
    --update-only) UPDATE_ONLY="true"; shift ;;
    --allow-insecure-http) ALLOW_INSECURE_HTTP="true"; shift ;;
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
  http://*)
    if [ "$ALLOW_INSECURE_HTTP" != "true" ]; then
      echo "HTTP outside localhost requires --allow-insecure-http" >&2
      exit 2
    fi
    echo "Warning: enrollment credentials and telemetry will cross the network without TLS." >&2
    ;;
  *) echo "Server must use HTTPS (except localhost)" >&2; exit 2 ;;
esac

if [ "$(uname -s)" != "Linux" ]; then
  echo "The automatic installer supports Linux" >&2
  exit 1
fi
if [ -r /etc/os-release ]; then
  . /etc/os-release
  case "${VERSION_CODENAME:-}" in
    stretch|buster|bullseye)
      echo "Warning: ${PRETTY_NAME:-this OS release} no longer receives normal security support." >&2
      echo "Re-image with a current Raspberry Pi OS release before using this tracker outside local testing." >&2
      ;;
  esac
fi

case "$(uname -m)" in
  armv6l) TARGET="linux-armv6" ;;
  armv7l|armv8l) TARGET="linux-armv7" ;;
  aarch64|arm64) TARGET="linux-arm64" ;;
  x86_64|amd64) TARGET="linux-amd64" ;;
  *) echo "Unsupported Linux architecture: $(uname -m)" >&2; exit 1 ;;
esac

for command in curl sha256sum install systemctl; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Required command is missing: $command" >&2
    exit 1
  fi
done

ARTIFACT="vehinode-agent-${AGENT_VERSION}-${TARGET}"
BASE="${SERVER%/}/agent/releases/${AGENT_VERSION}"
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT INT TERM

download() {
  url="$1"
  destination="$2"
  attempt=1
  while [ "$attempt" -le 8 ]; do
    case "$SERVER" in
      https://*)
        if curl -fL --proto '=https' --tlsv1.2 --connect-timeout 20 --continue-at - "$url" -o "$destination"; then
          return 0
        fi
        ;;
      *)
        if curl -fL --connect-timeout 20 --continue-at - "$url" -o "$destination"; then
          return 0
        fi
        ;;
    esac
    if [ "$attempt" -eq 8 ]; then
      echo "Download failed after ${attempt} attempts: ${url}" >&2
      return 1
    fi
    attempt=$((attempt + 1))
    echo "Transfer interrupted; resuming download (attempt ${attempt}/8)..." >&2
    sleep "$attempt"
  done
}

download "${BASE}/${ARTIFACT}" "${TMPDIR}/${ARTIFACT}"
download "${BASE}/${ARTIFACT}.sha256" "${TMPDIR}/${ARTIFACT}.sha256"
(cd "$TMPDIR" && sha256sum -c "${ARTIFACT}.sha256")
install -m 0755 "${TMPDIR}/${ARTIFACT}" /usr/local/bin/vehinode-agent

set -- install --server "$SERVER"
if [ "$UPDATE_ONLY" = "true" ]; then
  set -- "$@" --update-only
else
  set -- "$@" --token "$TOKEN"
fi
if [ "$ALLOW_INSECURE_HTTP" = "true" ]; then
  set -- "$@" --allow-insecure-http
fi
/usr/local/bin/vehinode-agent "$@"

/usr/local/bin/vehinode-agent doctor || true
echo "Review hardware: sudo vehinode-agent devices"
echo "Full removal: sudo vehinode-agent uninstall"
