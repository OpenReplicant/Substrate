# Shared by the scripts: where things are, which runtime and engine, compose over kernel's stack.
# shellcheck shell=sh

ROOT=$(cd "$(dirname "$0")/.." && pwd)
case "$ROOT" in */scripts) ROOT=$(dirname "$ROOT") ;; esac   # sourced from scripts/runtime/
KERNEL="$ROOT/repos/kernel"
MORPHOGEN="$ROOT/repos/morphogen"
ENV_FILE="$ROOT/.env"
PATH="$ROOT/.state/bin:$PATH"   # pinned tools bootstrap.sh installs (nomad)
export PATH

# a value as written in .env (empty if unset)
env_file_value() {
  [ -f "$ENV_FILE" ] || return 0   # no .env yet (before bootstrap or up.sh): every setting is empty
  sed -n "s/^$1=//p" "$ENV_FILE" | tail -1 | tr -d '"'"'"
}

# is NAME one of the secrets (deploy/secrets.txt)?
is_secret() { grep -q "^$1[[:space:]]" "$ROOT/deploy/secrets.txt"; }
secret_names() { sed -n 's/^\([A-Z][A-Z0-9_]*\)[[:space:]].*/\1/p' "$ROOT/deploy/secrets.txt"; }

# a setting's value (empty if unset): the environment wins; a secret comes from the secrets slot (S-31)
env_value() {
  eval "current=\${$1:-}"
  if [ -n "$current" ]; then printf '%s' "$current"; return; fi
  if [ "${SECRETS:-env}" != env ] && is_secret "$1"; then sec_get "$1"; return; fi
  env_file_value "$1"
}

# put every secret into this process's environment, for compose's ${...} and the tools container. Only needed
# when secrets are not in .env; values stay in memory.
secrets_export() {
  [ "${SECRETS:-env}" = env ] && return 0
  [ -n "${_SECRETS_EXPORTED:-}" ] && return 0
  for name in $(secret_names); do
    v=$(sec_get "$name") || return 1
    [ -n "$v" ] && export "$name=$v"
  done
  _SECRETS_EXPORTED=1
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

SECRETS=$(env_file_value SECRETS)
SECRETS=${SECRETS:-env}
[ -f "$ROOT/scripts/secrets/$SECRETS.sh" ] || { echo "SECRETS '$SECRETS' has no scripts/secrets/$SECRETS.sh" >&2; exit 1; }
# The secrets slot's verbs: sec_start, sec_stop, sec_get NAME, sec_put NAME (value on stdin), sec_status (S-31)
. "$ROOT/scripts/secrets/$SECRETS.sh"

compose() {
  secrets_export || return 1
  "$ENGINE" compose -f "$KERNEL/deploy/compose.yaml" -f "$ROOT/deploy/compose.yaml" --env-file "$ENV_FILE" "$@"
}

say() { printf '\n== %s\n' "$*"; }

# The runtime's verbs: rt_up, rt_down, rt_status, rt_logs SERVICE (S-16)
. "$ROOT/scripts/runtime/$RUNTIME.sh"
