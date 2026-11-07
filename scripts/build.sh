#!/bin/sh
# Build substrate's images, all inside the container engine (S-19). With no argument, builds what is missing
# and rebuilds kernel and tools (cheap: the engine's layer cache keeps unchanged steps).
#
#   scripts/build.sh                    # kernel, db (kernel's Postgres image), front door, tools, and Backstage if missing
#   scripts/build.sh kernel|db|caddy|tools|backstage
set -eu
. "$(dirname "$0")/lib.sh"

# How each engine names a locally built image, so other images and Nomad can refer to it.
local_name() { if [ "$ENGINE" = podman ]; then printf 'localhost/%s' "$1"; else printf '%s' "$1"; fi; }

build_kernel() {
  "$ENGINE" build -q -t knowledge-kernel:local "$KERNEL" >/dev/null && echo "  knowledge-kernel:local"
}
# A registry image by its full name, so Podman never has to guess a registry for a short one.
full_name() {
  case "$1" in
    localhost/*|*.*/*|*:*/*) printf '%s' "$1" ;;
    */*) printf 'docker.io/%s' "$1" ;;
    *) printf 'docker.io/library/%s' "$1" ;;
  esac
}

# Kernel's Postgres image: pgvector, pg_cron, pgmq, pgGraph (kernel D-94; S-24). Compose builds it as its own
# db service; Nomad runs the tagged image. Either way it is rebuilt here, so a newer kernel Dockerfile takes effect.
build_db() {
  if [ "$RUNTIME" = compose ]; then
    compose build -q db >/dev/null && echo "  db (kernel's Postgres image, built by compose)"
  else
    "$ENGINE" build -q -t knowledge-kernel-db:local "$KERNEL/deploy/postgres" >/dev/null && echo "  knowledge-kernel-db:local"
  fi
}

# The front door (S-20): the stock Caddy image, or Caddy built with the plugins in deploy/caddy/plugins.txt.
build_caddy() {
  image=$(env_value FRONT_DOOR_IMAGE); image=${image:-localhost/substrate-caddy:local}
  base=$(env_value CADDY_IMAGE); base=$(full_name "${base:-caddy:2.11.7-alpine}")
  version=${base##*:}; version=${version%-alpine}
  if grep -qv '^[[:space:]]*\(#\|$\)' "$ROOT/deploy/caddy/plugins.txt"; then
    "$ENGINE" build -q -t "$image" --build-arg "CADDY_VERSION=$version" \
      -f "$ROOT/deploy/caddy/Containerfile" "$ROOT/deploy/caddy" >/dev/null \
      && echo "  $image (Caddy $version with: $(grep -v '^[[:space:]]*\(#\|$\)' "$ROOT/deploy/caddy/plugins.txt" | awk '{print $1}' | tr '\n' ' '))"
  else
    "$ENGINE" image inspect "$base" >/dev/null 2>&1 || "$ENGINE" pull -q "$base" >/dev/null
    "$ENGINE" tag "$base" "$image" && echo "  $image (Caddy $version, no plugins)"
  fi
}
build_tools() {
  "$ENGINE" build -q -t substrate-tools:local --build-arg "KERNEL_IMAGE=$(local_name knowledge-kernel:local)" \
    -f "$ROOT/deploy/tools/Containerfile" "$ROOT/deploy/tools" >/dev/null && echo "  substrate-tools:local"
}
# What the Backstage image was built from: its package files, so a dependency added here triggers a rebuild.
backstage_hash() { cat "$ROOT"/services/backstage/package.json "$ROOT"/services/backstage/packages/*/package.json | cksum | cut -d' ' -f1; }

build_backstage() {
  image=$(env_value BACKSTAGE_IMAGE); image=${image:-localhost/substrate-backstage:local}
  echo "  $image: building in containers (the first build takes several minutes)"
  "$ENGINE" build -t "$image" --label "substrate.backstage.packages=$(backstage_hash)" \
    -f "$ROOT/services/backstage/Containerfile" "$ROOT/services/backstage"
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
  caddy) build_caddy ;;
  tools) build_tools ;;
  backstage) build_backstage ;;
  all)
    build_kernel
    build_db
    build_caddy
    build_tools
    image=$(env_value BACKSTAGE_IMAGE); image=${image:-localhost/substrate-backstage:local}
    built=$("$ENGINE" image inspect -f '{{index .Config.Labels "substrate.backstage.packages"}}' "$image" 2>/dev/null || true)
    if [ -n "$built" ] && [ "$built" = "$(backstage_hash)" ]; then
      echo "  $image present (rebuild: scripts/build.sh backstage)"
    else
      build_backstage   # missing, or its package files changed since it was built
    fi ;;
  *) echo "usage: scripts/build.sh [kernel|db|caddy|tools|backstage]" >&2; exit 1 ;;
esac
