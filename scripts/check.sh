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
probe "http://127.0.0.1:8080/ui/views.json" && ok "kernel      http://127.0.0.1:8080/ui/ (MCP at /mcp)" || bad "kernel UI does not answer (scripts/logs.sh kernel, caddy)"
running=$(rt_status 2>/dev/null | awk 'NR > 1 {print $1}' | tr '\n' ' ')
for s in db kernel caddy; do
  case "$running" in *"-$s-"*) ;; *) bad "service $s is not running (scripts/logs.sh $s)" ;; esac
done
extra=$(printf '%s\n' $running | grep -v -e '-db-' -e '-kernel-' -e '-caddy-' -e '-init-' || true)
[ -z "$extra" ] && ok "only the core runs (db, kernel, caddy)" || note "also running, outside the core: $(echo $extra)"

say "Wiring"
if st=$(sec_status 2>&1); then ok "secrets ($SECRETS): $st"; else bad "secrets ($SECRETS): $st"; fi
"$ROOT/scripts/tools.sh" status >/dev/null 2>&1 && ok "tools container running (bin/ wrappers work)" || bad "tools container not running: scripts/tools.sh start"
if out=$(KK_ADMIN_URL="postgresql://postgres:$(env_value POSTGRES_PASSWORD)@127.0.0.1:$(env_value KK_DB_PORT)/kk" \
         "$ROOT/bin/in-tools" python3 "$ROOT/scripts/map_check.py" 2>&1); then ok "map in kernel: $out"
else bad "map in kernel: $(echo "$out" | tail -1) (scripts/map.sh)"; fi
"$ROOT/bin/gitleaks" version >/dev/null 2>&1 && ok "gitleaks in the tools container: $("$ROOT/bin/gitleaks" version 2>/dev/null)" || bad "bin/gitleaks does not run"
if [ -f "$ROOT/.mcp.json" ] && grep -q '"kernel"' "$ROOT/.mcp.json"; then
  grep -q "$ROOT/bin/kernel-mcp" "$ROOT/.mcp.json" && ok "kernel MCP entry runs bin/kernel-mcp" \
    || bad "kernel MCP entry does not use bin/kernel-mcp: python3 scripts/point_harness.py ."
else
  note "no kernel MCP entry here (scripts/up.sh writes it into the project it connects)"
fi

if [ -f "$ROOT/docs/build.yaml" ]; then
  note "spec: $(python3 "$ROOT/scripts/spec.py" next --short 2>&1)"
fi

say "Upstream clones"
for repo in kernel morphogen; do
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
