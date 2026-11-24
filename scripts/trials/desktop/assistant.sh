#!/bin/sh
# The desktop as an environment, end to end (S-206), against the running stack; the map-diagram trial's Playwright image.
# Secrets by name only: the kernel's KK_JWT_SECRET (the agent's token) and the person's password
# (scripts/kernel.sh person NAME).   scripts/trials/desktop/assistant.sh [NAME]
set -eu
cd "$(dirname "$0")/../../.."
NAME=${1:-owner}
IMAGE=localhost/substrate-trial-browser:1.64.1
podman image exists "$IMAGE" || podman build -q -t "$IMAGE" -f scripts/trials/map-diagram/Containerfile scripts/trials/map-diagram >/dev/null
KK_JWT_SECRET=$(sed -n 's/^KK_JWT_SECRET=//p' .env | tail -1) KK_PERSON=$NAME KK_PASSWORD=$(cat ".state/kernel/person-$NAME.password") \
  exec podman run --rm --network=host --userns=keep-id -e KK_JWT_SECRET -e KK_PERSON -e KK_PASSWORD -v "$PWD:/w:Z" -w /w "$IMAGE" \
  python3 scripts/trials/desktop/assistant.py
