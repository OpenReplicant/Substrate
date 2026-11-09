#!/bin/sh
# The map into Workbench: substrate:catalog reads catalog-info.yaml, then substrate:drift compares it with what the
# repository has and raises each gap for review. Safe to run any time: an unchanged file adds nothing.
# The PostToolUse hook in .claude/settings.json runs it after an edit to a catalog-info.yaml (its name, map.sh, is
# what names that hook in the map: posttooluse-map).
#
#   scripts/map.sh              # this repository
#   scripts/map.sh --hook       # from the hook (the tool call's JSON on stdin): quiet, never fails the session
set -eu
. "$(dirname "$0")/lib.sh"

if [ "${1:-}" = --hook ]; then
  python3 -c 'import json, sys; p = (json.load(sys.stdin).get("tool_input") or {}).get("file_path") or ""; sys.exit(0 if p.endswith("catalog-info.yaml") else 1)' || exit 0
  "$ROOT/scripts/tools.sh" status >/dev/null 2>&1 || exit 0
  { "$ROOT/scripts/workbench.sh" extract substrate:catalog && "$ROOT/scripts/workbench.sh" extract substrate:drift; } >/dev/null 2>&1 || true
  exit 0
fi
for x in catalog drift; do
  "$ROOT/scripts/workbench.sh" extract "substrate:$x" | python3 -c 'import json, sys; d = json.load(sys.stdin); print("  substrate:'"$x"'", "ok" if d.get("ok") else "FAILED: " + str(d.get("error")), *(d.get("log") or []))'
done
