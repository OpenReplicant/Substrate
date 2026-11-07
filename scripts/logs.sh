#!/bin/sh
# A service's recent logs, by the runtime in .env.
#
#   scripts/logs.sh SERVICE     # db or postgres, init, kernel, caddy, bifrost, backstage, prometheus
set -eu
. "$(dirname "$0")/lib.sh"

service=${1:?usage: scripts/logs.sh SERVICE}
if [ "$RUNTIME" = nomad ] && [ "$service" = db ]; then service=postgres; fi
if [ "$RUNTIME" = compose ] && [ "$service" = postgres ]; then service=db; fi
rt_logs "$service"
