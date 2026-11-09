#!/bin/sh
# Bring up the stack (S-57): Postgres, PostgREST, the Workbench server, Caddy; then Workbench's schema, substrate's
# plugin and its extractors, the claude-code agent's account, and this project's Claude Code wiring.
#
#   scripts/up.sh
set -eu
. "$(dirname "$0")/lib.sh"

"$ROOT/scripts/settings.sh"
"$ROOT/scripts/build.sh"

say "Services ($RUNTIME)"
rt_up
"$ROOT/scripts/tools.sh" start

say "Workbench: its database, the core schema, substrate's plugin (workbench/BRIEF.md)"
i=0
until "$ROOT/scripts/workbench.sh" migrate >/dev/null 2>&1; do
  i=$((i + 1)); [ $i -gt 30 ] && { echo "  Postgres did not take the migration: scripts/logs.sh db" >&2; "$ROOT/scripts/workbench.sh" migrate; exit 1; }
  sleep 2
done
echo "  migrated"
"$ROOT/scripts/workbench.sh" plugin load "$ROOT/plugins/substrate" | python3 -c 'import json, sys; d = json.load(sys.stdin); print("  plugin", d["plugin"], d["version"], "types:", ", ".join(t["type"] for t in d["types"]))'
"$ROOT/scripts/graph.sh"                                  # the graph views, from the terms the plugin just loaded
wait_for() {   # what url logs
  i=0
  until curl -fsS -o /dev/null "$2" 2>/dev/null; do
    i=$((i + 1)); [ $i -gt 60 ] && { echo "  $1 did not answer at $2: scripts/logs.sh $3" >&2; exit 1; }
    sleep 2
  done
  echo "  $1 ok: $2"
}
wait_for API "http://127.0.0.1:8080/api/" postgrest
wait_for server "http://127.0.0.1:8080/wb/api/health" workbench
wait_for shell "http://127.0.0.1:8080/" caddy
# the map lives in Workbench (plugins/substrate/MAP.md); an empty one starts from the committed export
if [ "$("$ROOT/scripts/map.sh" count 2>/dev/null || echo 0)" = 0 ]; then
  "$ROOT/scripts/map.sh" import | head -1
fi
for x in map claude-code morphogen choices; do   # the map's relations, what the repository has, verdicts, choices
  "$ROOT/scripts/workbench.sh" extract "substrate:$x" | python3 -c 'import json, sys; d = json.load(sys.stdin); print("  substrate:'"$x"'", "ok" if d.get("ok") else "FAILED: " + str(d.get("error")), *(d.get("log") or []))'
done
"$ROOT/scripts/observe.sh" || echo "  observing stopped (above); the gaps are as they were"   # what runs, the gaps, inferences

say "Agents and this project's Claude Code"
"$ROOT/scripts/workbench.sh" user list | python3 -c 'import json, sys; sys.exit(0 if any(u["name"] == "claude-code" for u in json.load(sys.stdin)) else 1)' \
  || "$ROOT/scripts/workbench.sh" user add claude-code --role editor --agent >/dev/null
echo "  agent claude-code (editor): it signs in by token"
python3 "$ROOT/scripts/harness.py" status | python3 -c 'import json, sys; d = json.load(sys.stdin); sys.exit(0 if d["workbench_current"] else 1)' \
  || python3 "$ROOT/scripts/harness.py" apply | python3 -c 'import json, sys; d = json.load(sys.stdin); print("  wired: Workbench MCP in .mcp.json; backup in", d["backup"] or "(none: new file)")'

say "Up"
"$ROOT/scripts/check.sh" || true
echo
echo "  Workbench: http://127.0.0.1:8080/ (a person: scripts/workbench.sh user add NAME, run in your own terminal)"
if [ -f "$ROOT/docs/spec.md" ]; then
  echo "  The spec is in place (docs/spec.md): the next Claude Code session here continues its build plan."
fi
