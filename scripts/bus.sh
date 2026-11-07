#!/bin/sh
# The message bus (S-21): create or update the `substrate` database, pgmq and its queues (deploy/bus/queues.txt).
# Runs scripts/bus.py in the tools container against Postgres on 127.0.0.1, so it is the same for both runtimes.
# scripts/up.sh runs it; run it by hand after adding a queue.
#
#   scripts/bus.sh
set -eu
. "$(dirname "$0")/lib.sh"

"$ROOT/scripts/tools.sh" start >/dev/null
i=0
until env_value SUBSTRATE_BUS_PASSWORD | KK_ADMIN_URL="postgresql://postgres:$(env_value POSTGRES_PASSWORD)@127.0.0.1:$(env_value KK_DB_PORT)/kk" \
      "$ROOT/bin/in-tools" python3 "$ROOT/scripts/bus.py"; do
  i=$((i + 1)); [ $i -gt 20 ] && { echo "  the bus could not be set up (is Postgres up? scripts/logs.sh db)" >&2; exit 1; }
  sleep 3
done
