#!/bin/sh
# The desktop spike's browser run (S-200), in the map-diagram trial's pinned Playwright image (Playwright 1.64.1), on the
# host's network so it reaches the front door on 127.0.0.1. Signs in as NAME (default owner) with the password that
# scripts/kernel.sh person NAME kept; the password goes to the container by name, never on a command line.
#
#   scripts/trials/desktop/run.sh [NAME]
set -eu
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
ENGINE=${CONTAINER_ENGINE:-podman}
IMAGE=localhost/substrate-trial-browser:1.64.1
NAME=${1:-owner}
"$ENGINE" image exists "$IMAGE" 2>/dev/null || "$ENGINE" build -q -t "$IMAGE" -f "$ROOT/scripts/trials/map-diagram/Containerfile" "$ROOT/scripts/trials/map-diagram" >/dev/null
KK_PERSON=$NAME KK_PASSWORD=$(cat "$ROOT/.state/kernel/person-$NAME.password") \
  exec "$ENGINE" run --rm --network=host --userns=keep-id -e KK_PERSON -e KK_PASSWORD -v "$ROOT:/w:Z" -w /w "$IMAGE" \
  python3 scripts/trials/desktop/run.py
