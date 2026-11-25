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
CORE="db gateway ollama kernel ui caddy mcp-router mcp-kernel desktop mcp-desktop"

say "Services ($RUNTIME on $ENGINE)"
running=$(rt_status 2>/dev/null | awk 'NR > 1 {print $1}' | tr '\n' ' ')
for s in $CORE; do
  case "$running" in *"-$s-"*) ;; *) bad "service $s is not running (scripts/logs.sh $s)" ;; esac
done
extra=$(printf '%s\n' $running | grep -v -e '-db-' -e '-gateway-' -e '-ollama-' -e '-kernel-' -e '-ui-' -e '-caddy-' -e '-mcp-' -e '-desktop-' -e '-llm-' || true)
[ -z "$extra" ] && ok "only the core runs ($CORE)" || note "also running, outside the core: $(echo $extra)"
if "$ROOT/bin/in-tools" python3 -c '
import sys; sys.path.insert(0, "scripts")
from db import connect, DB; from gateway import settings
with connect(settings(), DB) as c:
    have = {r[0] for r in c.execute("select name from pg_available_extensions where name in (%s, %s, %s, %s)", ("vector", "pg_cron", "pgmq", "graph"))}
    print(", ".join(sorted(have)))' >/tmp/substrate-check.$$ 2>&1; then
  ok "postgres    127.0.0.1:$(env_value DB_PORT)/kernel, one database (extensions available: $(cat /tmp/substrate-check.$$))"
else bad "the kernel database does not answer: $(tail -1 /tmp/substrate-check.$$) (scripts/up.sh)"; fi
rm -f /tmp/substrate-check.$$
if out=$("$ROOT/bin/in-tools" python3 -c '
import sys; sys.path[:0] = ["scripts", "."]
from environment import db as envdb; from db import connect, DB; from gateway import settings
with connect(settings(), DB) as c:
    done = {r[0] for r in c.execute("select name from public.env_migration")} if c.execute("select to_regclass($$public.env_migration$$)").fetchone()[0] else set()
    todo = sorted(f.name for f in envdb.SQL.glob("*.sql") if f.name not in done)
    if todo: raise SystemExit("schema not applied: " + ", ".join(todo))
    print("schema applied: " + ", ".join(sorted(done)))' 2>&1); then
  ok "environment schema $out"
else bad "the environment's schema: $(printf '%s\n' "$out" | tail -1) (bin/in-tools python3 scripts/db.py init)"; fi
# The Knowledge Kernel (S-154): the read model the UI and the agents' substrate profile answer from
if out=$("$ROOT/bin/in-tools" python3 -c '
import sys; sys.path[:0] = ["scripts", "."]
import psycopg; from db import kernel_url; from gateway import settings
with psycopg.connect(kernel_url(settings()), autocommit=True) as c:
    c.execute("set role kkm_view_substrate")
    e, w, n = c.execute("select (select count(*) from substrate.entity), (select count(*) from substrate.wholes), (select count(*) from api.claims where status in ($$normal$$, $$preferred$$))").fetchone()
    print(f"{e} entities, {w} wholes, {n} usable claims")' 2>&1); then
  ok "kernel      $out (MCP: scripts/kernel.sh login NAME, then mcp__kernel__*)"
else bad "the kernel: $(printf '%s\n' "$out" | tail -1) (scripts/kernel.sh init)"; fi
# The real-time environment (plan step 3c): signals, queues and proposals waiting for a person
if out=$("$ROOT/bin/in-tools" python3 -c '
import sys; sys.path[:0] = ["scripts", "."]
from db import connect, DB; from gateway import settings
with connect(settings(), DB) as c:
    s, q, a, w = c.execute("select (select count(*) from env.signal), (select count(*) from pgmq.meta), (select count(*) from env.actuator), (select count(*) from env.action where status = $$proposed$$)").fetchone()
    print(f"{s} signals, {q} queues, {a} actuators, {w} proposals waiting")' 2>&1); then
  ok "environment $out (bin/in-tools python3 scripts/env.py waiting)"
else bad "the environment: $(printf '%s\n' "$out" | tail -1) (bin/in-tools python3 scripts/db.py init)"; fi
# Probe with a provider this machine has: Bifrost answers 400 for one it has none of, before it checks the key
probe=openrouter/x:free; [ -z "$(env_value OPENROUTER_API_KEY)" ] && [ -n "$(env_value OLLAMA_URL)" ] && probe=ollama/x
# 000 is no answer yet: a gateway just recreated may restart once or twice before it reaches its database (podman 4.9's
# network DNS drops lookups while many containers start at once, S-169), so wait up to a minute for one
for _ in $(seq 1 30); do
  code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "http://127.0.0.1:$(env_value GATEWAY_PORT)/v1/chat/completions" -H 'Content-Type: application/json' -d "{\"model\":\"$probe\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}]}")
  [ "$code" = 000 ] || break; sleep 2
done
[ "$code" = "401" ] && ok "gateway     http://127.0.0.1:$(env_value GATEWAY_PORT)/ (Bifrost; a call without a key is refused)" || bad "the model gateway returned $code to a call without a key (scripts/logs.sh gateway)"
# The local models (S-169), when COMPOSE_PROFILES in .env turns them on
case ",$(env_value COMPOSE_PROFILES)," in *,llm,*)
  case "$running" in *-llm-*) ;; *) bad "service llm is not running (scripts/logs.sh llm)" ;; esac
  if [ "$("$ENGINE" inspect -f '{{.State.Health.Status}}' substrate-llm-1 2>/dev/null)" = healthy ]; then
    ok "llm         $(env_value LLM_MODEL) on llama.cpp, at the gateway as local/$(env_value LLM_ALIAS)"
  else note "llm         not healthy yet (a large model takes minutes to load; scripts/logs.sh llm)"; fi
  if [ -n "$(env_value LLM_FAST_MODEL)" ]; then
    if [ "$("$ENGINE" inspect -f '{{.State.Health.Status}}' substrate-llm-fast-1 2>/dev/null)" = healthy ]; then
      ok "llm-fast    $(env_value LLM_FAST_MODEL) on llama.cpp, at the gateway as fast/$(env_value LLM_FAST_ALIAS)"
    else note "llm-fast    not healthy yet (scripts/logs.sh llm-fast)"; fi
  fi ;;
esac
# The UI (S-140): its API answers from the store, under a CSP that allows scripts and styles from itself only
ui="http://127.0.0.1:$(env_value UI_PORT || true)"; [ "$ui" = "http://127.0.0.1:" ] && ui=http://127.0.0.1:8100
hdr=$(curl -s -D - -o /dev/null "$ui/api/wholes" 2>/dev/null | tr -d '\r')
case "$hdr" in
  *" 200 "*"script-src 'self'; style-src 'self'"*) ok "ui          $ui/ (maps at $ui/#/map/<id>; scripts and styles from itself only)" ;;
  *" 200 "*) bad "the UI answers without its CSP (ui/server.py)" ;;
  *) bad "the UI does not answer at $ui/api/wholes (scripts/logs.sh ui)" ;;
esac
# The front door (S-199): Caddy to the kernel's shell, with the kernel's own security headers on it
dport=$(env_value DESKTOP_PORT); dport=${dport:-8080}
desk=http://127.0.0.1:$dport   # DESKTOP_PORT; the apps stay on 8081 to 8083, which apps.json names (S-200)
hdr=$(curl -s -D - -o /dev/null "$desk/ui/" 2>/dev/null | tr -d '\r')
case "$hdr" in
  *" 200 "*"frame-src http://127.0.0.1:8081 http://127.0.0.1:8082 http://127.0.0.1:8083;"*"frame-ancestors 'none'"*)
    ok "desktop     $desk/ (the kernel's shell; frames only the apps in deploy/caddy/apps.json; sign in: scripts/kernel.sh person NAME)" ;;
  *" 200 "*) bad "the kernel's shell answers at $desk/ui/ without its CSP or the apps' frame-src (deploy/caddy/Caddyfile)" ;;
  *) bad "the kernel's shell does not answer at $desk/ui/ (scripts/logs.sh caddy, scripts/logs.sh kernel)" ;;
esac
# Its framed apps (S-200): each on an origin of its own, framable by the desktop only, with no X-Frame-Options left
for app in 8081:gateway 8082:maps 8083:mcp; do
  hdr=$(curl -s -D - -o /dev/null "http://127.0.0.1:${app%%:*}/" 2>/dev/null | tr -d '\r')
  case "$hdr" in
    *[Xx]-[Ff]rame-[Oo]ptions*) bad "app ${app#*:} at :${app%%:*} still sends X-Frame-Options (deploy/caddy/Caddyfile)" ;;
    *" 200 "*"frame-ancestors http://127.0.0.1:$dport http://localhost:$dport"*) ok "app ${app#*:}  http://127.0.0.1:${app%%:*}/ (framable by the desktop only)" ;;
    *) bad "app ${app#*:} at :${app%%:*} does not answer with frame-ancestors for the desktop (scripts/logs.sh caddy)" ;;
  esac
done

say "Wiring"
if st=$(sec_status 2>&1); then ok "secrets ($SECRETS): $st"; else bad "secrets ($SECRETS): $st"; fi
"$ROOT/scripts/tools.sh" status >/dev/null 2>&1 && ok "tools container running (bin/ wrappers work)" || bad "tools container not running: scripts/tools.sh start"
"$ROOT/bin/gitleaks" version >/dev/null 2>&1 && ok "gitleaks in the tools container: $("$ROOT/bin/gitleaks" version 2>/dev/null)" || bad "bin/gitleaks does not run"
# The catalog (S-176): every part an entry, every consumed API provided, every compose service described
if out=$("$ROOT/bin/in-tools" python3 "$ROOT/scripts/catalog.py" check --compose "$ROOT/deploy/compose.yaml" 2>&1); then
  ok "catalog     $(printf '%s\n' "$out" | head -1 | sed 's/^catalog: //'); fits, matches compose"
else bad "catalog: $(printf '%s\n' "$out" | grep FAIL | head -2 | sed 's/^ *FAIL *//' | tr '\n' ';') (bin/in-tools python3 scripts/catalog.py check --compose deploy/compose.yaml)"; fi
# where the local model server computes: its last device report (S-84)
dev=$(rt_logs ollama 2>/dev/null | grep 'msg="inference compute"' | tail -1 | sed -n 's/.*library=\([^ ]*\).*description="\([^"]*\)".*total="\([^"]*\)".*/\1 on \2, \3/p')
gpu=$(env_value OLLAMA_GPU)
if [ -n "$dev" ]; then note "local models: $dev${gpu:+ (OLLAMA_GPU=$gpu)}"
elif [ -n "$gpu" ]; then note "local models: OLLAMA_GPU=$gpu, but Ollama reported no GPU (scripts/logs.sh ollama)"
else note "local models: on the CPU (OLLAMA_GPU is empty)"; fi

say "Scripts"
unparsed=""
for f in "$ROOT"/scripts/*.sh "$ROOT"/scripts/*/*.sh "$ROOT"/bin/*; do
  [ -f "$f" ] && head -1 "$f" | grep -q '^#!/bin/sh' && { sh -n "$f" 2>/dev/null || unparsed="$unparsed ${f#"$ROOT"/}"; }
done
[ -z "$unparsed" ] && ok "every shell script parses (sh -n)" || bad "these do not parse:$unparsed"

echo
[ $fails -eq 0 ] && echo "All checks passed." || echo "$fails check(s) failed."
exit $fails
