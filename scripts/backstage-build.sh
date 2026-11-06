#!/bin/sh
# Build the Backstage image from services/backstage: Backstage's documented host build (install, type-check,
# bundle the backend), then its packages/backend/Dockerfile. Needs Node 22 or 24 with corepack.
#
#   scripts/backstage-build.sh
set -eu
. "$(dirname "$0")/lib.sh"

image=$(env_value BACKSTAGE_IMAGE)
image=${image:-localhost/substrate-backstage:local}
cd "$ROOT/services/backstage"

say "Backstage: install (first run takes several minutes)"
corepack enable >/dev/null 2>&1 || true
yarn install
say "Backstage: type-check and bundle the backend"
yarn tsc
yarn build:backend
say "Backstage: image $image ($ENGINE)"
"$ENGINE" build -t "$image" -f packages/backend/Dockerfile .
echo "Built $image. yarn.lock changed on the first install: commit it, so every machine installs the same versions."
