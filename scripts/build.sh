#!/bin/sh
# Substrate's images, all inside the container engine (S-19). With no argument: pull the published images (db, tools,
# kernel; S-167) and build only the ones that did not pull. SUBSTRATE_BUILD=1 (here or in .env) builds everything.
# A build is tagged with the published name, so compose finds it. Cheap to run again: the engine's layer cache keeps unchanged steps.
#
#   scripts/build.sh                    # pull, then build what is missing
#   SUBSTRATE_BUILD=1 scripts/build.sh  # build all of them
#   scripts/build.sh db|tools|kernel   # build that one
set -eu
. "$(dirname "$0")/lib.sh"

build_db() {
  "$ENGINE" build -q -t "$(image_ref db)" -f "$ROOT/deploy/postgres/Dockerfile" "$ROOT/deploy/postgres" >/dev/null \
    && echo "  $(image_ref db) (Postgres with pgvector, pg_cron, pgmq, pgGraph)"
}
build_tools() {
  "$ENGINE" build -q -t "$(image_ref tools)" -f "$ROOT/deploy/tools/Containerfile" "$ROOT/deploy/tools" >/dev/null \
    && echo "  $(image_ref tools)"
}

# The Knowledge Kernel's image (S-154), from its own repository's Dockerfile: cloned into repos/kernel as repos.yaml says
# when it is not there yet (repos/ is the upstream clones, gitignored). Behind a TLS-intercepting proxy the build needs
# the proxy's CA as a build secret (CA_BUNDLE=/path/ca.crt scripts/build.sh kernel).
build_kernel() {
  if [ ! -d "$ROOT/repos/kernel/.git" ]; then
    url=$(sed -n '/^kernel:/,/^[a-z]/s/^  url: *//p' "$ROOT/repos.yaml" | head -1)
    branch=$(sed -n '/^kernel:/,/^[a-z]/s/^  branch: *//p' "$ROOT/repos.yaml" | head -1)
    mkdir -p "$ROOT/repos" && git clone --quiet --branch "${branch:-main}" "$url" "$ROOT/repos/kernel"
  fi
  if [ -n "${CA_BUNDLE:-}" ]; then set -- --secret "id=ca,src=$CA_BUNDLE"; else set --; fi
  "$ENGINE" build -q "$@" -t "$(image_ref kernel)" -f "$ROOT/repos/kernel/Dockerfile" "$ROOT/repos/kernel" >/dev/null \
    && echo "  $(image_ref kernel) (kk, the kernel's modules, kernel-mcp)"
}

# pull what is published, build what is not
pull_or_build() {   # NAME
  ref=$(image_ref "$1")
  if rt_pull "$ref"; then echo "  $ref (pulled)"; else echo "  $1: not pulled ($ref), building"; "build_$1"; fi
}

say "Images ($ENGINE)"
force=${SUBSTRATE_BUILD:-$(env_value SUBSTRATE_BUILD)}
case "${1:-all}" in
  db) build_db ;;
  tools) build_tools ;;
  kernel) build_kernel ;;
  all)
    if [ "$force" = 1 ]; then
      build_db; build_tools; build_kernel
    else
      for n in db tools kernel; do pull_or_build "$n"; done
    fi ;;
  *) echo "usage: scripts/build.sh [db|tools|kernel]" >&2; exit 1 ;;
esac
