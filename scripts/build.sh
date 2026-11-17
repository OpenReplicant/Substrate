#!/bin/sh
# Build substrate's images, all inside the container engine (S-19). Cheap to run again: the engine's layer cache
# keeps unchanged steps.
#
#   scripts/build.sh                    # db (Postgres with its extensions), tools, companion
#   scripts/build.sh db|tools|companion
set -eu
. "$(dirname "$0")/lib.sh"

build_db() { compose build -q db >/dev/null && echo "  db (deploy/postgres)"; }
build_tools() {
  "$ENGINE" build -q -t substrate-tools:local -f "$ROOT/deploy/tools/Containerfile" "$ROOT/deploy/tools" >/dev/null \
    && echo "  substrate-tools:local"
}
build_companion() {
  "$ENGINE" build -q -t substrate-companion:local -f "$ROOT/deploy/companion/Containerfile" "$ROOT/deploy/companion" >/dev/null \
    && echo "  substrate-companion:local (Claude Code, tmux, the channel's Python)"
}

say "Images ($ENGINE)"
case "${1:-all}" in
  db) build_db ;;
  tools) build_tools ;;
  companion) build_companion ;;
  all) build_db; build_tools; build_companion ;;
  *) echo "usage: scripts/build.sh [db|tools|companion]" >&2; exit 1 ;;
esac
