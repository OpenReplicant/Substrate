#!/bin/sh
# Build substrate's images, all inside the container engine (S-19). Cheap to run again: the engine's layer cache
# keeps unchanged steps.
#
#   scripts/build.sh                    # db (Postgres with its extensions), tools, companion, kernel
#   scripts/build.sh db|tools|companion|voice|kernel
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
  "$ENGINE" build -q "$@" -t substrate-kernel:local -t localhost/substrate-kernel:local -f "$ROOT/repos/kernel/Dockerfile" "$ROOT/repos/kernel" >/dev/null \
    && echo "  substrate-kernel:local (kk, the kernel's modules, kernel-mcp)"
}

build_voice() {
  "$ENGINE" build -q -t substrate-voice:local -f "$ROOT/voice/Containerfile" "$ROOT/voice" >/dev/null \
    && echo "  substrate-voice:local (speech in and out: sherpa-onnx, kokoro-onnx)"
}

say "Images ($ENGINE)"
case "${1:-all}" in
  db) build_db ;;
  tools) build_tools ;;
  companion) build_companion ;;
  voice) build_voice ;;
  kernel) build_kernel ;;
  all) build_db; build_tools; build_companion; build_voice; build_kernel ;;
  *) echo "usage: scripts/build.sh [db|tools|companion|voice|kernel]" >&2; exit 1 ;;
esac
