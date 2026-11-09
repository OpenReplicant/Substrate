#!/bin/sh
# The tools container (S-19): one long-lived substrate-tools container that bin/ wrappers exec into. It runs
# as you, on the host network (it reaches Postgres at 127.0.0.1 like the rest of the harness), and sees only
# this checkout and any other project folders it is given, each at its own host path.
#
#   scripts/tools.sh start [PROJECT...]   # (re)create it if the folders it should see, or its image, have changed
#   scripts/tools.sh stop | status
set -eu
. "$(dirname "$0")/lib.sh"

NAME=substrate-tools

# Projects already connected (recorded one per line in .state/projects), plus any named now.
projects() {
  mkdir -p "$ROOT/.state"; touch "$ROOT/.state/projects"
  for p in "$@"; do (cd "$p" && pwd); done >> "$ROOT/.state/projects"
  sort -u "$ROOT/.state/projects" | grep -vx "$ROOT" > "$ROOT/.state/projects.tmp" || true
  mv "$ROOT/.state/projects.tmp" "$ROOT/.state/projects"
  cat "$ROOT/.state/projects"
}

running() { [ "$("$ENGINE" inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null)" = "true" ]; }

start() {
  list=$(projects "$@")
  want=$(printf '%s\n%s\n' "$ROOT" "$list" | cksum | cut -d' ' -f1)
  have=$("$ENGINE" inspect -f '{{index .Config.Labels "substrate.mounts"}}' "$NAME" 2>/dev/null || true)
  # a rebuilt image (scripts/build.sh) must replace the running container, or bin/ keeps running the old code
  img_want=$("$ENGINE" image inspect -f '{{.Id}}' "$(image)" 2>/dev/null || true)
  img_have=$("$ENGINE" inspect -f '{{.Image}}' "$NAME" 2>/dev/null || true)
  if running && [ "$want" = "$have" ] && [ "${img_want#sha256:}" = "${img_have#sha256:}" ]; then echo "  $NAME running"; return; fi
  "$ENGINE" rm -f "$NAME" >/dev/null 2>&1 || true
  mkdir -p "$ROOT/.state/uv-cache"
  set -- --detach --name "$NAME" --label "substrate.mounts=$want" --network host \
    --cap-drop ALL --security-opt no-new-privileges \
    --user "$(id -u):$(id -g)" \
    -e "HOME=$HOME" \
    -e "UV_CACHE_DIR=$ROOT/.state/uv-cache" -e "UV_PROJECT_ENVIRONMENT=$ROOT/.state/morphogen-venv" \
    -v "$ROOT:$ROOT" -w "$ROOT"
  if [ "$ENGINE" = podman ] && [ "$(id -u)" != 0 ]; then set -- "$@" --userns keep-id; fi   # files stay yours (rootless)
  for p in $list; do set -- "$@" -v "$p:$p"; done
  "$ENGINE" run "$@" "$(image)" >/dev/null
  echo "  $NAME started (sees $ROOT$(for p in $list; do printf ', %s' "$p"; done))"
}

image() { if [ "$ENGINE" = podman ]; then echo localhost/substrate-tools:local; else echo substrate-tools:local; fi; }

case "${1:-status}" in
  start) shift; start "$@" ;;
  stop) "$ENGINE" rm -f "$NAME" >/dev/null 2>&1 || true; echo "  $NAME stopped" ;;
  status) running && echo "running" || { echo "not running (scripts/tools.sh start)"; exit 1; } ;;
  *) echo "usage: scripts/tools.sh start [PROJECT...] | stop | status" >&2; exit 1 ;;
esac
