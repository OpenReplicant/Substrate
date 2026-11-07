# Shared by the scripts: where things are, which runtime and engine, compose over kernel's stack.
# shellcheck shell=sh

ROOT=$(cd "$(dirname "$0")/.." && pwd)
case "$ROOT" in */scripts) ROOT=$(dirname "$ROOT") ;; esac   # sourced from scripts/runtime/
KERNEL="$ROOT/repos/kernel"
MORPHOGEN="$ROOT/repos/morphogen"
ENV_FILE="$ROOT/.env"
PATH="$ROOT/.state/bin:$PATH"   # pinned tools bootstrap.sh installs (nomad)
export PATH

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

RUNTIME=$(env_value RUNTIME)
RUNTIME=${RUNTIME:-compose}
[ -f "$ROOT/scripts/runtime/$RUNTIME.sh" ] || { echo "RUNTIME '$RUNTIME' has no scripts/runtime/$RUNTIME.sh" >&2; exit 1; }

compose() {
  "$ENGINE" compose -f "$KERNEL/deploy/compose.yaml" -f "$ROOT/deploy/compose.yaml" --env-file "$ENV_FILE" "$@"
}

say() { printf '\n== %s\n' "$*"; }

# The runtime's verbs: rt_up, rt_down, rt_status, rt_logs SERVICE (S-16)
. "$ROOT/scripts/runtime/$RUNTIME.sh"
