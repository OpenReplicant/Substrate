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
CORE="db gateway ollama ui environment companion"

say "Services ($RUNTIME on $ENGINE)"
running=$(rt_status 2>/dev/null | awk 'NR > 1 {print $1}' | tr '\n' ' ')
for s in $CORE; do
  case "$running" in *"-$s-"*) ;; *) bad "service $s is not running (scripts/logs.sh $s)" ;; esac
done
extra=$(printf '%s\n' $running | grep -v -e '-db-' -e '-gateway-' -e '-ollama-' -e '-ui-' -e '-environment-' -e '-companion-' || true)
[ -z "$extra" ] && ok "only the core runs ($CORE)" || note "also running, outside the core: $(echo $extra)"
if "$ROOT/bin/in-tools" python3 -c '
import sys; sys.path.insert(0, "scripts")
from db import connect, DB; from gateway import settings
with connect(settings(), DB) as c:
    have = {r[0] for r in c.execute("select name from pg_available_extensions where name in (%s, %s, %s, %s)", ("vector", "pg_cron", "pgmq", "graph"))}
    print(", ".join(sorted(have)))' >/tmp/substrate-check.$$ 2>&1; then
  ok "postgres    127.0.0.1:$(env_value DB_PORT)/substrate (extensions available: $(cat /tmp/substrate-check.$$))"
else bad "the substrate database does not answer: $(tail -1 /tmp/substrate-check.$$) (scripts/up.sh)"; fi
rm -f /tmp/substrate-check.$$
if out=$("$ROOT/bin/in-tools" python3 -c '
import sys; sys.path[:0] = ["scripts", "."]
import store; from db import connect, DB; from gateway import settings
with connect(settings(), DB) as c:
    done = {r[0] for r in c.execute("select name from public.store_migration")}
    todo = sorted(f.name for f in store.SQL.glob("*.sql") if f.name not in done)
    if todo: raise SystemExit("schema not applied: " + ", ".join(todo))
    e, s, f, v = c.execute("select (select count(*) from store.entity), (select count(*) from store.statement), (select count(distinct f.statement_id) from store.flag f join store.statement st on st.id = f.statement_id where st.rank <> $$deprecated$$), (select count(*) from store.violation)").fetchone()
    stale = len(store.stale_file_spans(c, store.SQL.parent.parent))
    print(f"{e} entities, {s} statements, {f} flagged, {v} constraint violations, {stale} cited file lines changed")' 2>&1); then
  ok "store       $out (MCP: bin/in-tools python3 -m store.mcp)"
else bad "the store: $(printf '%s\n' "$out" | tail -1) (bin/in-tools python3 scripts/db.py init)"; fi
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
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "http://127.0.0.1:$(env_value GATEWAY_PORT)/v1/chat/completions" -H 'Content-Type: application/json' -d "{\"model\":\"$probe\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}]}")
[ "$code" = "401" ] && ok "gateway     http://127.0.0.1:$(env_value GATEWAY_PORT)/ (Bifrost; a call without a key is refused)" || bad "the model gateway returned $code to a call without a key (scripts/logs.sh gateway)"
# The companion (plan step 4, S-136): its session in tmux, and whether the owner's Claude login is in its home yet
if out=$(compose exec -T companion sh -c 'tmux has-session -t companion 2>/dev/null && echo session; test -s "$HOME/.claude/.credentials.json" && echo login; true' 2>/dev/null); then
  case "$out" in
    *session*login*) ok "companion   session running, logged in (scripts/companion.sh attach; talk at the UI's #/companion)" ;;
    *session*) note "companion   session running, not logged in yet: scripts/companion.sh login" ;;
    *) bad "companion   no session in its container (scripts/logs.sh companion)" ;;
  esac
else bad "companion   its container does not answer (scripts/logs.sh companion)"; fi
# The UI (S-140): its API answers from the store, under a CSP that allows scripts and styles from itself only
ui="http://127.0.0.1:$(env_value UI_PORT || true)"; [ "$ui" = "http://127.0.0.1:" ] && ui=http://127.0.0.1:8100
hdr=$(curl -s -D - -o /dev/null "$ui/api/wholes" 2>/dev/null | tr -d '\r')
case "$hdr" in
  *" 200 "*"script-src 'self'; style-src 'self'"*) ok "ui          $ui/ (maps at $ui/#/map/<id>; scripts and styles from itself only)" ;;
  *" 200 "*) bad "the UI answers without its CSP (ui/server.py)" ;;
  *) bad "the UI does not answer at $ui/api/wholes (scripts/logs.sh ui)" ;;
esac

say "Wiring"
if st=$(sec_status 2>&1); then ok "secrets ($SECRETS): $st"; else bad "secrets ($SECRETS): $st"; fi
"$ROOT/scripts/tools.sh" status >/dev/null 2>&1 && ok "tools container running (bin/ wrappers work)" || bad "tools container not running: scripts/tools.sh start"
"$ROOT/bin/gitleaks" version >/dev/null 2>&1 && ok "gitleaks in the tools container: $("$ROOT/bin/gitleaks" version 2>/dev/null)" || bad "bin/gitleaks does not run"
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
