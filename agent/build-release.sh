#!/bin/sh
set -eu

VERSION=${1:?usage: build-release.sh VERSION [OUTPUT_DIR]}
OUTPUT_DIR=${2:-dist}
mkdir -p "$OUTPUT_DIR"

build() {
  target=$1
  architecture=$2
  arm_version=$3
  output="$OUTPUT_DIR/vehinode-agent-$VERSION-$target"
  echo "Building $target"
  CGO_ENABLED=0 GOOS=linux GOARCH="$architecture" GOARM="$arm_version" \
    go build -trimpath -buildvcs=false \
    -ldflags "-s -w -X main.version=$VERSION -X main.buildTarget=$target" \
    -o "$output" ./cmd/vehinode-agent
  (cd "$OUTPUT_DIR" && sha256sum "$(basename "$output")") > "$output.sha256"
}

build linux-amd64 amd64 ""
build linux-arm64 arm64 ""
build linux-armv7 arm 7
build linux-armv6 arm 6
