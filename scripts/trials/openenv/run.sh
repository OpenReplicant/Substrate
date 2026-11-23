#!/bin/sh
# The OpenEnv spike (S-184, plan step 1): openenv 0.12.0 beside Claude Code, on the stack's Postgres (throwaway
# databases openenv_trial*). scripts/trials/openenv/run.sh [all|facts|p1|p3|p47]; results in .state/trials/openenv/.
set -eu
cd "$(dirname "$0")/../../.."

out=.state/trials/openenv; mkdir -p "$out"
podman image exists substrate-trial-openenv:local || podman build -t substrate-trial-openenv:local scripts/trials/openenv
POSTGRES_PASSWORD=$(sed -n "s/^POSTGRES_PASSWORD=//p" .env | tail -1); export POSTGRES_PASSWORD   # by name below, never on a command line
podman run --rm --network substrate_default -e POSTGRES_PASSWORD \
    -v "$PWD/scripts/trials/openenv/spike.py:/opt/spike.py:ro,Z" \
    substrate-trial-openenv:local python3 -I /opt/spike.py "${1:-all}" | tee -a "$out/results.jsonl"
