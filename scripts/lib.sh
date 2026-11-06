# Shared by the scripts: where things are, which container engine, compose over kernel's stack.
# shellcheck shell=sh

ROOT=$(cd "$(dirname "$0")/.." && pwd)
KERNEL="$ROOT/repos/kernel"
MORPHOGEN="$ROOT/repos/morphogen"
ENV_FILE="$ROOT/.env"

# a value from .env (empty if unset); the environment wins
env_value() {
  eval "current=\${$1:-}"
  if [ -n "$current" ]; then printf '%s' "$current"; return; fi
  [ -f "$ENV_FILE" ] && sed -n "s/^$1=//p" "$ENV_FILE" | tail -1 | tr -d '"'"'"
}

ENGINE=$(env_value CONTAINER_ENGINE)
ENGINE=${ENGINE:-podman}
case "$ENGINE" in
  docker|podman) ;;
  *) echo "CONTAINER_ENGINE must be docker or podman, not '$ENGINE'" >&2; exit 1 ;;
esac

compose() {
  "$ENGINE" compose -f "$KERNEL/deploy/compose.yaml" -f "$ROOT/deploy/compose.yaml" --env-file "$ENV_FILE" "$@"
}

say() { printf '\n== %s\n' "$*"; }
