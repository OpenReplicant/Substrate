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
CORE="db gateway ollama"

say "Services ($RUNTIME on $ENGINE)"
running=$(rt_status 2>/dev/null | awk 'NR > 1 {print $1}' | tr '\n' ' ')
for s in $CORE; do
  case "$running" in *"-$s-"*) ;; *) bad "service $s is not running (scripts/logs.sh $s)" ;; esac
done
extra=$(printf '%s\n' $running | grep -v -e '-db-' -e '-gateway-' -e '-ollama-' || true)
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
# Probe with a provider this machine has: Bifrost answers 400 for one it has none of, before it checks the key
probe=openrouter/x:free; [ -z "$(env_value OPENROUTER_API_KEY)" ] && [ -n "$(env_value OLLAMA_URL)" ] && probe=ollama/x
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "http://127.0.0.1:$(env_value GATEWAY_PORT)/v1/chat/completions" -H 'Content-Type: application/json' -d "{\"model\":\"$probe\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}]}")
[ "$code" = "401" ] && ok "gateway     http://127.0.0.1:$(env_value GATEWAY_PORT)/ (Bifrost; a call without a key is refused)" || bad "the model gateway returned $code to a call without a key (scripts/logs.sh gateway)"

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
