#!/bin/sh
# Build substrate's images, all inside the container engine (S-19). Cheap to run again: the engine's layer cache
# keeps unchanged steps.
#
#   scripts/build.sh                    # db (Postgres with its extensions), workbench (the server), graph (Ontop), tools
#   scripts/build.sh db|workbench|graph|tools
set -eu
. "$(dirname "$0")/lib.sh"

build_db() { compose build -q db >/dev/null && echo "  db (deploy/postgres)"; }
build_workbench() { compose build -q workbench >/dev/null && echo "  workbench (workbench/Containerfile)"; }
build_graph() { compose build -q graph >/dev/null && echo "  graph (deploy/ontop: Ontop with PgJDBC)"; }
build_tools() {
  "$ENGINE" build -q -t substrate-tools:local -f "$ROOT/deploy/tools/Containerfile" "$ROOT/deploy/tools" >/dev/null \
    && echo "  substrate-tools:local"
}

say "Images ($ENGINE)"
case "${1:-all}" in
  db) build_db ;;
  workbench) build_workbench ;;
  tools) build_tools ;;
  graph) build_graph ;;
  all) build_db; build_workbench; build_graph; build_tools ;;
  *) echo "usage: scripts/build.sh [db|workbench|graph|tools]" >&2; exit 1 ;;
esac
