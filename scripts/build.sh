#!/bin/sh
# Build substrate's images, all inside the container engine (S-19). Cheap to run again: the engine's layer cache
# keeps unchanged steps.
#
#   scripts/build.sh                    # db (Postgres with its extensions), tools
#   scripts/build.sh db|tools
set -eu
. "$(dirname "$0")/lib.sh"

build_db() { compose build -q db >/dev/null && echo "  db (deploy/postgres)"; }
build_tools() {
  "$ENGINE" build -q -t substrate-tools:local -f "$ROOT/deploy/tools/Containerfile" "$ROOT/deploy/tools" >/dev/null \
    && echo "  substrate-tools:local"
}

say "Images ($ENGINE)"
case "${1:-all}" in
  db) build_db ;;
  tools) build_tools ;;
  all) build_db; build_tools ;;
  *) echo "usage: scripts/build.sh [db|tools]" >&2; exit 1 ;;
esac
