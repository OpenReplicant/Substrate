#!/bin/sh
# Stop the stack. Data stays in its volumes; `scripts/down.sh --volumes` deletes it (asks first).
set -eu
. "$(dirname "$0")/lib.sh"

if [ "${1:-}" = "--volumes" ]; then
  printf 'Delete every volume (kernel claims, gateway config and logs, metrics)? Type yes: '
  read -r answer
  [ "$answer" = "yes" ] || { echo "Kept."; exit 1; }
  compose down --volumes
else
  compose down
fi
