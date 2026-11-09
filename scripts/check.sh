#!/bin/sh
# Is everything up and wired? Prints one line per check; exits non-zero if any fails.
#
#   scripts/check.sh
set -u
. "$(dirname "$0")/lib.sh"

fails=0
ok()   { printf '  ok    %s\n' "$*"; }
bad()  { printf '  FAIL  %s\n' "$*"; fails=$((fails + 1)); }
note() { printf '  note  %s\n' "$*"; }
probe() { curl -fsS -o /dev/null "$@" 2>/dev/null; }

say "Services ($RUNTIME on $ENGINE)"
code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:8080/api/")
[ "$code" = "200" ] && ok "api         http://127.0.0.1:8080/api/ (PostgREST, OpenAPI at the root)" || bad "the API returned $code (scripts/logs.sh postgrest)"
shell=$(curl -s "http://127.0.0.1:8080/")
case "$shell" in *'name="wb-plugin"'*) ok "shell       http://127.0.0.1:8080/ ($(printf '%s' "$shell" | grep -c 'name="wb-plugin"') plugin modules)" ;;
  *) bad "the shell is not served at / (scripts/logs.sh caddy)" ;; esac
if h=$(curl -fsS "http://127.0.0.1:8080/wb/api/health" 2>/dev/null); then
  ok "server      http://127.0.0.1:8080/wb/api/ ($(printf '%s' "$h" | python3 -c 'import json, sys; d = json.load(sys.stdin); print(("events relayed" if d["listening"] else "NOT listening") + ", jobs " + ("taken" if d["worker"] else "NOT taken") + ", plugins: " + ", ".join(p["id"] + (" (" + p["error"] + ")" if p.get("error") else "") for p in d["plugins"]))'))"
else bad "the Workbench server does not answer (scripts/logs.sh workbench)"; fi
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "http://127.0.0.1:8080/wb/api/mcp" -H 'Content-Type: application/json' -d '{}')
[ "$code" = "401" ] && ok "mcp         http://127.0.0.1:8080/wb/api/mcp (asks for a token)" || bad "the MCP endpoint returned $code without a token"
if n=$(curl -fsS --max-time 30 -H 'Accept: application/sparql-results+json' --data-urlencode 'query=SELECT (COUNT(?x) AS ?n) WHERE { ?x a <https://workbench.local/ns#Item> }' "http://127.0.0.1:8080/sparql" 2>/dev/null \
     | python3 -c 'import json, sys; print(json.load(sys.stdin)["results"]["bindings"][0]["n"]["value"])' 2>/dev/null); then
  ok "sparql      http://127.0.0.1:8080/sparql (Ontop, read-only; $n items, by reasoning over their classes)"
else bad "the graph endpoint does not answer at /sparql (scripts/logs.sh graph; scripts/graph.sh)"; fi
running=$(rt_status 2>/dev/null | awk 'NR > 1 {print $1}' | tr '\n' ' ')
for s in db caddy postgrest workbench graph; do
  case "$running" in *"-$s-"*) ;; *) bad "service $s is not running (scripts/logs.sh $s)" ;; esac
done
extra=$(printf '%s\n' $running | grep -v -e '-db-' -e '-caddy-' -e '-postgrest-' -e '-workbench-' -e '-graph-' || true)
[ -z "$extra" ] && ok "only the core runs (db, caddy, postgrest, workbench, graph)" || note "also running, outside the core: $(echo $extra)"

say "Wiring"
if st=$(sec_status 2>&1); then ok "secrets ($SECRETS): $st"; else bad "secrets ($SECRETS): $st"; fi
"$ROOT/scripts/tools.sh" status >/dev/null 2>&1 && ok "tools container running (bin/ wrappers work)" || bad "tools container not running: scripts/tools.sh start"
"$ROOT/bin/gitleaks" version >/dev/null 2>&1 && ok "gitleaks in the tools container: $("$ROOT/bin/gitleaks" version 2>/dev/null)" || bad "bin/gitleaks does not run"
if out=$("$ROOT/scripts/workbench.sh" token claude-code --hours 0.02 2>&1); then ok "agent claude-code can get a token (MCP's headersHelper)"; else bad "no token for claude-code: $out"; fi
hs=$(python3 "$ROOT/scripts/harness.py" status)
printf '%s' "$hs" | python3 -c 'import json, sys; d = json.load(sys.stdin); sys.exit(0 if "workbench" in d["mcp_servers"] else 1)' \
  && ok "Claude Code here: MCP servers $(printf '%s' "$hs" | python3 -c 'import json, sys; print(", ".join(json.load(sys.stdin)["mcp_servers"]))')" \
  || bad "Claude Code here has no Workbench MCP entry: python3 scripts/harness.py apply"
printf '%s' "$hs" | python3 -c 'import json, sys; sys.exit(0 if not json.load(sys.stdin)["kernel_hooks"] else 1)' || note "kernel's hooks are still in .claude/settings.local.json: python3 scripts/harness.py apply"
gaps=$("$ROOT/bin/in-tools" true >/dev/null 2>&1 && curl -s "http://127.0.0.1:8080/api/decisions?status=eq.open&select=id" -H "Authorization: Bearer $("$ROOT/scripts/workbench.sh" token claude-code --hours 0.02 2>/dev/null)" | python3 -c 'import json, sys; print(len(json.load(sys.stdin)))' 2>/dev/null || echo "?")
note "review lane: $gaps open"

if [ -f "$ROOT/docs/build.yaml" ]; then
  note "spec: $(python3 "$ROOT/scripts/spec.py" next --short 2>&1)"
if [ -f "$ROOT/docs/build.yaml" ]; then
  python3 -c 'import sys, yaml; yaml.safe_load(open(sys.argv[1]))' "$ROOT/docs/build.yaml" 2>/dev/null \
    && ok "docs/build.yaml parses as YAML" || bad "docs/build.yaml is not valid YAML (python3 -c 'import yaml; yaml.safe_load(open(\"docs/build.yaml\"))')"
fi
if ls "$ROOT"/.state/contracts/*--*.json >/dev/null 2>&1; then
  c=$(python3 -c '
import json, sys
runs = [json.load(open(f)) for f in sys.argv[1:]]
bad = [r["interface"] + " with " + r["filler"] for r in runs if not r["passed"]]
oldest = min(r["ran_at"] for r in runs)[:16]
print(("FAIL " + ", ".join(bad)) if bad else f"{len(runs)} runs, all pass; oldest {oldest}")' "$ROOT"/.state/contracts/*--*.json)
  case "$c" in FAIL*) bad "contracts: ${c#FAIL } (scripts/contract.sh INTERFACE FILLER)" ;; *) ok "contracts: $c (scripts/contract.sh all)" ;; esac
else note "contracts: none run yet (scripts/contract.sh all)"; fi
fi

say "Upstream clones"
for repo in morphogen kernel; do
  dir="$ROOT/repos/$repo"
  [ -d "$dir/.git" ] || { [ $repo = kernel ] || bad "repos/$repo missing (scripts/bootstrap.sh)"; continue; }   # kernel: an option, cloned on request
  checked=$(sed -n "/^$repo:/,/^[a-z]/s/^  checked: \([0-9a-f]*\).*/\1/p" "$ROOT/repos.yaml")
  head=$(git -C "$dir" rev-parse HEAD); branch=$(git -C "$dir" rev-parse --abbrev-ref HEAD)
  dirty=$(git -C "$dir" status --porcelain | wc -l | tr -d ' ')
  if [ "$head" = "$checked" ]; then ok "$repo on $branch at the checked commit ($dirty changed files)"
  else note "$repo on $branch at $(git -C "$dir" rev-parse --short HEAD), checked ${checked%"${checked#???????}"} ($dirty changed files)"; fi
done

echo
[ $fails -eq 0 ] && echo "All checks passed." || echo "$fails check(s) failed."
exit $fails
