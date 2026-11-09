#!/bin/sh
# Bring up the stack and connect a project to kernel (default: this repository).
#
#   scripts/up.sh [PROJECT_DIR]
#
# Steps: .env (secrets generated once) -> images, built in containers (S-19) -> kernel's stack (Postgres,
# kernel, its Caddy) by the runtime in .env -> wait until kernel answers -> the tools container, seeing the
# project -> kk up --no-stack inside it (logins, MCP, skill, hooks, reading the project into .state/artifacts),
# with the project's Claude Code files pointing at bin/ (--commands-dir) -> the map into kernel.
set -eu
. "$(dirname "$0")/lib.sh"

project=$(cd "${1:-$ROOT}" && pwd)
[ -d "$KERNEL/.git" ] || { echo "repos/kernel is missing: run scripts/bootstrap.sh" >&2; exit 1; }

"$ROOT/scripts/settings.sh"
"$ROOT/scripts/build.sh"

say "Services ($RUNTIME)"
mkdir -p "$ROOT/.state/artifacts"
rt_up

say "Waiting for kernel"
i=0
until curl -fsS -o /dev/null "http://127.0.0.1:8080/ui/views.json" 2>/dev/null; do
  i=$((i + 1)); [ $i -gt 120 ] && { echo "  kernel did not answer at http://127.0.0.1:8080/ui/: scripts/logs.sh kernel" >&2; exit 1; }
  sleep 2
done
echo "  kernel ok"

say "Workbench: its database, the core schema, substrate's plugin (workbench/BRIEF.md)"
"$ROOT/scripts/tools.sh" start "$project"
"$ROOT/scripts/workbench.sh" migrate
"$ROOT/scripts/workbench.sh" plugin load "$ROOT/plugins/substrate" | python3 -c 'import json, sys; d = json.load(sys.stdin); print("  plugin", d["plugin"], d["version"], "types:", ", ".join(t["type"] for t in d["types"]))'
i=0
until curl -fsS -o /dev/null "http://127.0.0.1:8080/api/" 2>/dev/null; do
  i=$((i + 1)); [ $i -gt 60 ] && { echo "  the API did not answer at http://127.0.0.1:8080/api/: scripts/logs.sh postgrest" >&2; exit 1; }
  sleep 2
done
echo "  API ok: http://127.0.0.1:8080/api/ (a person: scripts/workbench.sh user add NAME)"
i=0
until curl -fsS -o /dev/null "http://127.0.0.1:8080/wb/api/health" 2>/dev/null; do
  i=$((i + 1)); [ $i -gt 60 ] && { echo "  the Workbench server did not answer: scripts/logs.sh workbench" >&2; exit 1; }
  sleep 2
done
echo "  server ok: http://127.0.0.1:8080/wb/api/health"
for x in catalog claude-code drift; do      # substrate's own map, what the repository has, and the gaps between them
  "$ROOT/scripts/workbench.sh" extract "substrate:$x" | python3 -c 'import json, sys; d = json.load(sys.stdin); print("  substrate:'"$x"'", "ok" if d.get("ok") else "FAILED: " + str(d.get("error")), *(d.get("log") or []))'
done

say "Kernel: logins and the project ($project)"
KK_ADMIN_URL="postgresql://postgres:$(env_value POSTGRES_PASSWORD)@127.0.0.1:$(env_value KK_DB_PORT)/kk" \
KK_JWT_SECRET="$(env_value KK_JWT_SECRET)" \
  "$ROOT/bin/kk" up --no-stack --commands-dir "$ROOT/bin" "$project"   # Claude Code runs bin/'s wrappers (kernel D-95)

say "The map into kernel (catalog-info.yaml)"
"$ROOT/scripts/map.sh" "$ROOT"
[ "$project" = "$ROOT" ] || [ ! -f "$project/catalog-info.yaml" ] || "$ROOT/scripts/map.sh" "$project"

say "Up"
"$ROOT/scripts/check.sh" || true
echo
echo "  Kernel: http://127.0.0.1:8080/ui/ (sign in as owner with the password kk up printed above)"
if [ -f "$ROOT/docs/spec.md" ]; then
  echo "  The spec is in place (docs/spec.md): the next Claude Code session here continues its build plan"
  echo "  (python3 scripts/spec.py status; delete docs/spec.md to stop that)."
fi
