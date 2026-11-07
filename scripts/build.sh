#!/bin/sh
# Build substrate's images, all inside the container engine (S-19). With no argument, builds what is missing
# and rebuilds kernel and tools (cheap: the engine's layer cache keeps unchanged steps).
#
#   scripts/build.sh                    # kernel, kernel-db (Nomad), tools, and Backstage if missing
#   scripts/build.sh kernel|db|tools|backstage
set -eu
. "$(dirname "$0")/lib.sh"

# How each engine names a locally built image, so other images and Nomad can refer to it.
local_name() { if [ "$ENGINE" = podman ]; then printf 'localhost/%s' "$1"; else printf '%s' "$1"; fi; }

build_kernel() {
  "$ENGINE" build -q -t knowledge-kernel:local "$KERNEL" >/dev/null && echo "  knowledge-kernel:local"
}
build_db() {
  "$ENGINE" build -q -t knowledge-kernel-db:local "$KERNEL/deploy/postgres" >/dev/null && echo "  knowledge-kernel-db:local"
}
build_tools() {
  "$ENGINE" build -q -t substrate-tools:local --build-arg "KERNEL_IMAGE=$(local_name knowledge-kernel:local)" \
    -f "$ROOT/deploy/tools/Containerfile" "$ROOT/deploy/tools" >/dev/null && echo "  substrate-tools:local"
}
build_backstage() {
  image=$(env_value BACKSTAGE_IMAGE); image=${image:-localhost/substrate-backstage:local}
  echo "  $image: building in containers (the first build takes several minutes)"
  "$ENGINE" build -t "$image" -f "$ROOT/services/backstage/Containerfile" "$ROOT/services/backstage"
  # keep the lock file the build resolved, so every machine installs the same versions
  if [ ! -f "$ROOT/services/backstage/yarn.lock" ]; then
    id=$("$ENGINE" create "$image")
    "$ENGINE" cp "$id:/app/yarn.lock" "$ROOT/services/backstage/yarn.lock"
    "$ENGINE" rm "$id" >/dev/null
    echo "  wrote services/backstage/yarn.lock from the build: commit it"
  fi
}

say "Images ($ENGINE)"
case "${1:-all}" in
  kernel) build_kernel ;;
  db) build_db ;;
  tools) build_tools ;;
  backstage) build_backstage ;;
  all)
    build_kernel
    [ "$RUNTIME" = nomad ] && build_db   # compose builds kernel's Postgres image itself
    build_tools
    image=$(env_value BACKSTAGE_IMAGE); image=${image:-localhost/substrate-backstage:local}
    if "$ENGINE" image inspect "$image" >/dev/null 2>&1; then
      echo "  $image present (rebuild: scripts/build.sh backstage)"
    else
      build_backstage
    fi ;;
  *) echo "usage: scripts/build.sh [kernel|db|tools|backstage]" >&2; exit 1 ;;
esac
