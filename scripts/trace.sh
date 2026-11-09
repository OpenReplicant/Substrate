#!/bin/sh
# The chain behind one part, from Workbench (scripts/trace.py): observed, declared, each gap and its decision.
#
#   scripts/trace.sh NAME        # e.g. setup
set -eu
. "$(dirname "$0")/lib.sh"

secrets_export
WORKBENCH_ADMIN_URL="postgresql://postgres:$(env_value POSTGRES_PASSWORD)@127.0.0.1:$(env_value KK_DB_PORT)/postgres" \
  exec "$ROOT/bin/in-tools" env WORKBENCH_ADMIN_URL="postgresql://postgres:$(env_value POSTGRES_PASSWORD)@127.0.0.1:$(env_value KK_DB_PORT)/postgres" \
  python3 "$ROOT/scripts/trace.py" "${1:?usage: scripts/trace.sh NAME}"
