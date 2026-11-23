#!/bin/sh
# A service's recent logs, by the runtime in .env.
#
#   scripts/logs.sh SERVICE     # db, gateway, ollama, kernel, ui, caddy, llm, llm-fast
set -eu
. "$(dirname "$0")/lib.sh"

rt_logs "${1:?usage: scripts/logs.sh SERVICE}"
