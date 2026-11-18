#!/bin/sh
# The map-diagram trial's run, in Playwright 1.64.1 (2026-10-22; its Containerfile, built once), with no network.
# Before it: bin/in-tools python3 scripts/trials/map-diagram/fetch.py and .../cases.py
set -eu
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
ENGINE=${CONTAINER_ENGINE:-podman}
IMAGE=localhost/substrate-trial-browser:1.64.1
"$ENGINE" image exists "$IMAGE" 2>/dev/null || "$ENGINE" build -q -t "$IMAGE" -f "$ROOT/scripts/trials/map-diagram/Containerfile" "$ROOT/scripts/trials/map-diagram" >/dev/null
exec "$ENGINE" run --rm --network=none --userns=keep-id -v "$ROOT:/w:Z" -w /w "$IMAGE" \
  python3 scripts/trials/map-diagram/run.py
