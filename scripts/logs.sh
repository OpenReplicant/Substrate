#!/bin/sh
# A service's recent logs, by the runtime in .env.
#
#   scripts/logs.sh SERVICE     # db, postgrest, workbench, graph, caddy
set -eu
. "$(dirname "$0")/lib.sh"

rt_logs "${1:?usage: scripts/logs.sh SERVICE}"
