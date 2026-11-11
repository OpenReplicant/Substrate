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
# Ontop retries its database connection on a cold start, so give it up to a minute before calling it down
for _ in 1 2 3 4 5 6 7 8 9 10 11 12; do curl -fs -o /dev/null --max-time 5 "http://127.0.0.1:8080/sparql?query=ASK%7B%7D" && break; sleep 5; done
if n=$(curl -fsS --max-time 30 -H 'Accept: application/sparql-results+json' --data-urlencode 'query=SELECT (COUNT(?x) AS ?n) WHERE { ?x a <https://workbench.local/ns#Item> }' "http://127.0.0.1:8080/sparql" 2>/dev/null \
     | python3 -c 'import json, sys; print(json.load(sys.stdin)["results"]["bindings"][0]["n"]["value"])' 2>/dev/null); then
  ok "sparql      http://127.0.0.1:8080/sparql (Ontop, read-only; $n items, by reasoning over their classes)"
else bad "the graph endpoint does not answer at /sparql (scripts/logs.sh graph; scripts/graph.sh)"; fi
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "http://127.0.0.1:$(env_value GATEWAY_PORT)/v1/chat/completions" -H 'Content-Type: application/json' -d '{"model":"openrouter/x:free","messages":[{"role":"user","content":"hi"}]}')
[ "$code" = "401" ] && ok "gateway     http://127.0.0.1:$(env_value GATEWAY_PORT)/ (Bifrost; a call without a key is refused)" || bad "the model gateway returned $code to a call without a key (scripts/logs.sh gateway)"
running=$(rt_status 2>/dev/null | awk 'NR > 1 {print $1}' | tr '\n' ' ')
for s in db caddy postgrest workbench graph gateway ollama; do
  case "$running" in *"-$s-"*) ;; *) bad "service $s is not running (scripts/logs.sh $s)" ;; esac
done
extra=$(printf '%s\n' $running | grep -v -e '-db-' -e '-caddy-' -e '-postgrest-' -e '-workbench-' -e '-graph-' -e '-gateway-' -e '-ollama-' || true)
[ -z "$extra" ] && ok "only the core runs (db, caddy, postgrest, workbench, graph, gateway, ollama)" || note "also running, outside the core: $(echo $extra)"

say "Wiring"
if st=$(sec_status 2>&1); then ok "secrets ($SECRETS): $st"; else bad "secrets ($SECRETS): $st"; fi
"$ROOT/scripts/tools.sh" status >/dev/null 2>&1 && ok "tools container running (bin/ wrappers work)" || bad "tools container not running: scripts/tools.sh start"
"$ROOT/bin/gitleaks" version >/dev/null 2>&1 && ok "gitleaks in the tools container: $("$ROOT/bin/gitleaks" version 2>/dev/null)" || bad "bin/gitleaks does not run"
if out=$("$ROOT/scripts/workbench.sh" token claude-code --hours 0.02 2>&1); then ok "agent claude-code can get a token (MCP's headersHelper)"; else bad "no token for claude-code: $out"; fi
hs=$(python3 "$ROOT/scripts/harness.py" status)
printf '%s' "$hs" | python3 -c 'import json, sys; d = json.load(sys.stdin); sys.exit(0 if "workbench" in d["mcp_servers"] else 1)' \
  && ok "Claude Code here: MCP servers $(printf '%s' "$hs" | python3 -c 'import json, sys; print(", ".join(json.load(sys.stdin)["mcp_servers"]))')" \
  || bad "Claude Code here has no Workbench MCP entry: python3 scripts/harness.py apply"
printf '%s' "$hs" | python3 -c 'import json, sys; sys.exit(0 if json.load(sys.stdin)["workbench_current"] else 1)' || note "Workbench's MCP entry in .mcp.json is out of date: python3 scripts/harness.py apply"
gaps=$("$ROOT/bin/in-tools" true >/dev/null 2>&1 && curl -s "http://127.0.0.1:8080/api/decisions?status=eq.open&select=id" -H "Authorization: Bearer $("$ROOT/scripts/workbench.sh" token claude-code --hours 0.02 2>/dev/null)" | python3 -c 'import json, sys; print(len(json.load(sys.stdin)))' 2>/dev/null || echo "?")
note "review lane: $gaps open"
# streams (streams.yaml, spec section 10): each handler by rank, with its calls and how often it answered
ladder=$(curl -s "http://127.0.0.1:8080/api/handler?select=slug,rank,calls,answers,measured&order=rank" -H "Authorization: Bearer $("$ROOT/scripts/workbench.sh" token claude-code --hours 0.02 2>/dev/null)" \
  | python3 -c 'import json, sys; print("; ".join("%s %s (%s/%s answered%s)" % (h["rank"], h["slug"], h["answers"], h["calls"], "" if h["measured"] else ", unmeasured") for h in json.load(sys.stdin)) or "none declared")' 2>/dev/null || echo "?")
note "ladder: $ladder"
vecs=$(curl -s "http://127.0.0.1:8080/api/rpc/recall" -H 'Content-Type: application/json' -H "Authorization: Bearer $("$ROOT/scripts/workbench.sh" token claude-code --hours 0.02 2>/dev/null)" \
  -d '{"q": "model gateway", "lim": 5, "depth": 2}' | python3 -c 'import json, sys; d = json.load(sys.stdin); print(len(d), "hits for \"model gateway\" by words and the graph")' 2>/dev/null || echo "?")
note "recall: $vecs (scripts/recall.sh QUERY adds meaning)"
# where the local model server computes: its last device report (S-84)
dev=$(rt_logs ollama 2>/dev/null | grep 'msg="inference compute"' | tail -1 | sed -n 's/.*library=\([^ ]*\).*description="\([^"]*\)".*total="\([^"]*\)".*/\1 on \2, \3/p')
# or, once its start is out of the log's tail, what share of its loaded models sits in GPU memory
[ -n "$dev" ] || dev=$(curl -fsS --max-time 5 "http://127.0.0.1:$(env_value OLLAMA_PORT)/api/ps" 2>/dev/null | python3 -c '
import json, sys
ms = json.load(sys.stdin).get("models") or []
size, vram = sum(m.get("size", 0) for m in ms), sum(m.get("size_vram", 0) for m in ms)
print("%d%% of %d loaded model(s) in GPU memory" % (round(100 * vram / size), len(ms)) if size and vram else "")' 2>/dev/null)
gpu=$(env_value OLLAMA_GPU)
if [ -n "$dev" ]; then note "local models: $dev${gpu:+ (OLLAMA_GPU=$gpu)}"
elif [ -n "$gpu" ]; then note "local models: OLLAMA_GPU=$gpu, but Ollama reported no GPU (scripts/logs.sh ollama)"
else note "local models: on the CPU (OLLAMA_GPU is empty)"; fi

if [ -f "$ROOT/docs/build.yaml" ]; then
  note "spec: $(python3 "$ROOT/scripts/spec.py" next --short 2>&1)"
m=$("$ROOT/scripts/map.sh" check 2>&1) && ok "map: $m" || note "map: $m"
o=$("$ROOT/scripts/map.sh" owners 2>/dev/null | head -1) && note "files: ${o%%;*} (scripts/map.sh owners: the rest are the judge's)"
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

say "Scripts"
unparsed=""
for f in "$ROOT"/scripts/*.sh "$ROOT"/scripts/*/*.sh "$ROOT"/scripts/trials/*/*.sh "$ROOT"/bin/*; do
  [ -f "$f" ] && head -1 "$f" | grep -q '^#!/bin/sh' && { sh -n "$f" 2>/dev/null || unparsed="$unparsed ${f#"$ROOT"/}"; }
done
[ -z "$unparsed" ] && ok "every shell script parses (sh -n)" || bad "these do not parse:$unparsed"

say "Upstream clones"
for repo in $(sed -n 's/^\([a-z][a-z0-9_-]*\):$/\1/p' "$ROOT/repos.yaml"); do
  dir="$ROOT/repos/$repo"
  [ -d "$dir/.git" ] || { bad "repos/$repo missing (scripts/bootstrap.sh)"; continue; }
  checked=$(sed -n "/^$repo:/,/^[a-z]/s/^  checked: \([0-9a-f]*\).*/\1/p" "$ROOT/repos.yaml")
  head=$(git -C "$dir" rev-parse HEAD); branch=$(git -C "$dir" rev-parse --abbrev-ref HEAD)
  dirty=$(git -C "$dir" status --porcelain | wc -l | tr -d ' ')
  if [ "$head" = "$checked" ]; then ok "$repo on $branch at the checked commit ($dirty changed files)"
  else note "$repo on $branch at $(git -C "$dir" rev-parse --short HEAD), checked ${checked%"${checked#???????}"} ($dirty changed files)"; fi
done

echo
[ $fails -eq 0 ] && echo "All checks passed." || echo "$fails check(s) failed."
exit $fails
