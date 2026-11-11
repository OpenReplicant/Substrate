#!/bin/sh
# The map, held in Workbench (plugins/substrate/MAP.md). Edit it there: the shell, or MCP's save_item, retire_item
# and restore_item on `component` items. This script derives what follows from it and moves it to and from files:
#
#   scripts/map.sh                         # relations from the map (substrate:map), then drift and the reasoner
#   scripts/map.sh export [DOMAIN [FILE]]  # the map as a catalog file (default: substrate, catalog-info.yaml)
#   scripts/map.sh check [DOMAIN [FILE]]   # does the file still match the map (exit 1 if not)
#   scripts/map.sh count [DOMAIN]          # how many entities stand in a domain's map
#   scripts/map.sh owners [DOMAIN]         # the tracked files no part claims (morphogen.dev/change): the judge's
#   scripts/map.sh import [FILE] [--force] # a catalog file into the map; refused if it would overwrite edits made in
#                                          # Workbench, unless --force (a new machine's first up.sh does this)
#   scripts/map.sh --hook                  # from the PostToolUse hook after an MCP write (JSON on stdin): quiet
#
# The hook in .claude/settings.json runs it after save_item, retire_item or restore_item on a component (its name,
# map.sh, is what names that hook in the map: posttooluse-map). Morphogen reads the exported file from the base
# commit, so a map change reaches the judge when its export is committed.
set -eu
. "$(dirname "$0")/lib.sh"

derive() {
  for x in map drift reasoner; do
    "$ROOT/scripts/workbench.sh" extract "substrate:$x" | python3 -c 'import json, sys; d = json.load(sys.stdin); print("  substrate:'"$x"'", "ok" if d.get("ok") else "FAILED: " + str(d.get("error")), *(d.get("log") or []))'
  done
  "$ROOT/scripts/streams.sh" run    # drift's gaps up their ladder (streams.yaml)
  "$ROOT/scripts/recall.sh" || echo "  recall's vectors were not made (above); words and the graph still answer"
}
mapfile() {
  "$ROOT/bin/in-tools" env PYTHONPATH="$ROOT/workbench:$ROOT/plugins/substrate" WB_SUBSTRATE_ROOT="$ROOT" \
    WORKBENCH_ADMIN_URL="postgresql://postgres:$(env_value POSTGRES_PASSWORD)@127.0.0.1:$(env_value DB_PORT)/postgres" \
    python3 "$ROOT/plugins/substrate/substrate_map.py" "$@"
}

case "${1:-}" in
  --hook)
    started=$(date +%s.%N)   # this run, recorded for handlers:run (stream claude-code-tools, scripts/calls.py)
    trap 'python3 "$ROOT/scripts/calls.py" record claude-code-tools posttooluse-map "$started" $?' EXIT
    python3 -c 'import json, sys; d = json.load(sys.stdin); t = (d.get("tool_input") or {}).get("type"); sys.exit(0 if t == "component" else 1)' || exit 0
    "$ROOT/scripts/tools.sh" status >/dev/null 2>&1 || exit 0
    derive >/dev/null 2>&1 || true
    exit 0 ;;
  export|check|count|owners)
    mapfile "$@" ;;
  import)
    file=catalog-info.yaml; force=""
    shift
    for a in "$@"; do case "$a" in --force) force="--input force=1" ;; *) file=$a ;; esac; done
    # shellcheck disable=SC2086
    "$ROOT/scripts/workbench.sh" extract substrate:catalog --input "file=$file" $force | python3 -c 'import json, sys; d = json.load(sys.stdin); print("  substrate:catalog", "ok" if d.get("ok") else "FAILED: " + str(d.get("error")), *(d.get("log") or [])); sys.exit(0 if d.get("ok") else 1)'
    derive ;;
  "")
    derive ;;
  *)
    sed -n '2,18p' "$0"; exit 2 ;;
esac
