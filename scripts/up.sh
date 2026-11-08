#!/bin/sh
# Bring up the whole stack and connect a project to kernel (default: this repository, S-10).
#
#   scripts/up.sh [PROJECT_DIR]
#
# Steps: .env (secrets generated once) -> the gateway's config -> images, built in containers (S-19) -> every
# service, by the runtime in .env (compose or nomad, S-16) -> wait until each answers -> the tools container,
# seeing the project -> kk up --no-stack inside it (logins, MCP, skill, hooks, reading the project into
# .state/artifacts), with the project's Claude Code files pointing at bin/ (--commands-dir).
set -eu
. "$(dirname "$0")/lib.sh"

project=$(cd "${1:-$ROOT}" && pwd)
[ -d "$KERNEL/.git" ] || { echo "repos/kernel is missing: run scripts/bootstrap.sh" >&2; exit 1; }

"$ROOT/scripts/settings.sh"

say "Gateway config"
python3 "$ROOT/scripts/render_bifrost.py"

"$ROOT/scripts/build.sh"

say "Services ($RUNTIME)"
mkdir -p "$ROOT/.state/artifacts" "$ROOT/.state/otel"
chmod 777 "$ROOT/.state/otel"      # the collector runs as a non-root user and writes Claude Code's events here
rt_up

say "Waiting for each service"
wait_for() {   # name url
  i=0
  until curl -fsS -o /dev/null "$2" 2>/dev/null; do
    i=$((i + 1)); [ $i -gt 120 ] && { echo "  $1 did not answer at $2: scripts/logs.sh $3" >&2; return 1; }
    sleep 2
  done
  echo "  $1 ok"
}
wait_for kernel "http://127.0.0.1:8080/ui/views.json" kernel
wait_for gateway "http://127.0.0.1:$(env_value BIFROST_PORT)/health" bifrost
wait_for map "http://127.0.0.1:$(env_value BACKSTAGE_PORT)/.backstage/health/v1/readiness" backstage
wait_for console "http://127.0.0.1:8080/console/" console

say "Message bus"
"$ROOT/scripts/bus.sh"

say "Kernel: logins and the project ($project)"
"$ROOT/scripts/tools.sh" start "$project"
KK_ADMIN_URL="postgresql://postgres:$(env_value POSTGRES_PASSWORD)@127.0.0.1:$(env_value KK_DB_PORT)/kk" \
KK_JWT_SECRET="$(env_value KK_JWT_SECRET)" \
  "$ROOT/bin/kk" up --no-stack --commands-dir "$ROOT/bin" "$project"   # Claude Code runs bin/'s wrappers (kernel D-95)
python3 "$ROOT/scripts/telemetry.py" on --project "$project"     # its metrics, events and traces to the collector (S-28)

say "The map into kernel (catalog-info.yaml, S-33)"
"$ROOT/scripts/map.sh" "$ROOT"
[ "$project" = "$ROOT" ] || [ ! -f "$project/catalog-info.yaml" ] || "$ROOT/scripts/map.sh" "$project"

say "Up"
"$ROOT/scripts/check.sh" || true
echo
echo "  Console: http://127.0.0.1:8080/console/ (sign in as owner with the password kk up printed above)"
if [ -f "$ROOT/docs/spec.md" ]; then
  echo "  The spec is in place (docs/spec.md): the next Claude Code session here continues its build plan"
  echo "  (python3 scripts/spec.py status; delete docs/spec.md to stop that)."
fi
