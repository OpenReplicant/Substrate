#!/bin/sh
# Build substrate's images, all inside the container engine (S-19). Cheap to run again: the engine's layer cache
# keeps unchanged steps.
#
#   scripts/build.sh                 # kernel, db (kernel's Postgres image), tools
#   scripts/build.sh kernel|db|tools
set -eu
. "$(dirname "$0")/lib.sh"

# How each engine names a locally built image, so other images can refer to it.
local_name() { if [ "$ENGINE" = podman ]; then printf 'localhost/%s' "$1"; else printf '%s' "$1"; fi; }

build_kernel() {
  "$ENGINE" build -q -t knowledge-kernel:local "$KERNEL" >/dev/null && echo "  knowledge-kernel:local"
}
# Kernel's Postgres image: pgvector, pg_cron, pgmq, pgGraph (kernel D-94; S-24), built by compose as its db service.
build_db() {
  compose build -q db >/dev/null && echo "  db (kernel's Postgres image, built by compose)"
}
build_tools() {
  "$ENGINE" build -q -t substrate-tools:local --build-arg "KERNEL_IMAGE=$(local_name knowledge-kernel:local)" \
    -f "$ROOT/deploy/tools/Containerfile" "$ROOT/deploy/tools" >/dev/null && echo "  substrate-tools:local"
}

say "Images ($ENGINE)"
case "${1:-all}" in
  kernel) build_kernel ;;
  db) build_db ;;
  tools) build_tools ;;
  all) build_kernel; build_db; build_tools ;;
  *) echo "usage: scripts/build.sh [kernel|db|tools]" >&2; exit 1 ;;
esac
