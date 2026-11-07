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

bport=$(env_value BIFROST_PORT); mport=$(env_value BACKSTAGE_PORT); pport=$(env_value PROMETHEUS_PORT)

say "Services ($RUNTIME on $ENGINE)"
if [ "$RUNTIME" = nomad ]; then
  nomad node status 2>/dev/null | grep -q ready && ok "nomad agent ready at $NOMAD_ADDR" || bad "nomad agent not ready ($NOMAD_ADDR)"
  nomad job status -short substrate 2>/dev/null | grep -q 'running' && ok "nomad job substrate running" || bad "nomad job substrate is not running"
fi
probe "http://127.0.0.1:8080/ui/views.json" && ok "kernel      http://127.0.0.1:8080/ui/" || bad "kernel UI does not answer"
probe "http://127.0.0.1:$bport/health" && ok "gateway     http://127.0.0.1:$bport/" || bad "gateway does not answer"
probe "http://127.0.0.1:$mport/.backstage/health/v1/readiness" && ok "map         http://127.0.0.1:$mport/" || bad "Backstage does not answer"
probe "http://127.0.0.1:$pport/-/ready" && ok "prometheus  http://127.0.0.1:$pport/" || bad "Prometheus does not answer"

say "Wiring"
curl -fsS "http://127.0.0.1:$bport/metrics" 2>/dev/null | grep -q '^bifrost_\|^# HELP bifrost_' \
  && ok "gateway exposes bifrost_* metrics" || note "no bifrost_* metrics yet (they appear after the first request)"
curl -fsS "http://127.0.0.1:$pport/api/v1/query?query=up%7Bjob%3D%22bifrost%22%7D" 2>/dev/null | grep -q '"value":\[[^]]*,"1"\]' \
  && ok "prometheus scrapes the gateway" || bad "prometheus target 'bifrost' is not up"
if [ "$RUNTIME" = nomad ]; then
  curl -fsS "http://127.0.0.1:$pport/api/v1/query?query=up%7Bjob%3D%22nomad%22%7D" 2>/dev/null | grep -q '"value":\[[^]]*,"1"\]' \
    && ok "prometheus scrapes Nomad's allocation metrics" || bad "prometheus target 'nomad' is not up"
fi
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "http://127.0.0.1:$mport/api/mcp-actions/v1" \
  -H "Authorization: Bearer $(env_value BACKSTAGE_MCP_TOKEN)" -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"check","version":"0"}}}')
[ "$code" = "200" ] && ok "Backstage MCP answers with the token" || bad "Backstage MCP initialize returned $code"
"$ROOT/scripts/tools.sh" status >/dev/null 2>&1 && ok "tools container running (bin/ wrappers work)" || bad "tools container not running: scripts/tools.sh start"
"$ROOT/bin/gitleaks" version >/dev/null 2>&1 && ok "gitleaks in the tools container: $("$ROOT/bin/gitleaks" version 2>/dev/null)" || bad "bin/gitleaks does not run"
if [ -f "$ROOT/.mcp.json" ] && grep -q '"kernel"' "$ROOT/.mcp.json"; then
  grep -q "$ROOT/bin/kernel-mcp" "$ROOT/.mcp.json" && ok "kernel MCP entry runs bin/kernel-mcp" \
    || bad "kernel MCP entry does not use bin/kernel-mcp: python3 scripts/point_harness.py ."
else
  note "no kernel MCP entry here (scripts/up.sh writes it into the project it connects)"
fi
"$ROOT/scripts/gateway.py" status >/dev/null 2>&1 && ok "Claude Code: $("$ROOT/scripts/gateway.py" status)" || note "Claude Code: $("$ROOT/scripts/gateway.py" status 2>&1)"

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
