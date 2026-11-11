#!/bin/sh
# Morphogen's verdicts into Workbench (substrate:morphogen): its evidence log, chain checked, as verdict items.
# The PostToolUse hook in .claude/settings.json runs it after a Morphogen tool call (its name, verdicts.sh, names
# that hook in the map: posttooluse-verdicts).
#
#   scripts/verdicts.sh            # this repository's log (<git common dir>/morphogen/evidence.db)
#   scripts/verdicts.sh --hook     # from the hook: quiet, never fails the session
set -eu
. "$(dirname "$0")/lib.sh"

if [ "${1:-}" = --hook ]; then
  started=$(date +%s.%N)   # this run, recorded for handlers:run (stream claude-code-tools, scripts/calls.py)
  trap 'python3 "$ROOT/scripts/calls.py" record claude-code-tools posttooluse-verdicts "$started" $?' EXIT
  "$ROOT/scripts/tools.sh" status >/dev/null 2>&1 || exit 0
  "$ROOT/scripts/workbench.sh" extract substrate:morphogen >/dev/null 2>&1 || true
  exit 0
fi
"$ROOT/scripts/workbench.sh" extract substrate:morphogen | python3 -c 'import json, sys; d = json.load(sys.stdin); print("  substrate:morphogen", "ok" if d.get("ok") else "FAILED: " + str(d.get("error")), *(d.get("log") or []))'
