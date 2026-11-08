#!/bin/sh
# Stop the stack, by the runtime in .env. Data stays; `scripts/down.sh --volumes` deletes it (asks first).
set -eu
. "$(dirname "$0")/lib.sh"

for a in "$@"; do
  if [ "$a" = "--volumes" ]; then
    printf 'Delete all data (kernel claims, artifacts)? Type yes: '
    read -r answer
    [ "$answer" = "yes" ] || { echo "Kept."; exit 1; }
  fi
done
rt_down "$@"
