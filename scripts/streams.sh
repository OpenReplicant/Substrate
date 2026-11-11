#!/bin/sh
# Substrate's streams (streams.yaml) through Workbench's handlers plugin (plugins/handlers/README.md; spec section 10).
#
#   scripts/streams.sh            # declare streams.yaml, then run every stream
#   scripts/streams.sh run        # run every stream: new inputs up their route, calls scored, handlers re-ranked
set -eu
. "$(dirname "$0")/lib.sh"

show() { python3 -c 'import json, sys; d = json.load(sys.stdin); print("  handlers:'"$1"'", "ok" if d.get("ok") else "FAILED: " + str(d.get("error")), *(d.get("log") or []))'; }
case "${1:-}" in
  "") "$ROOT/scripts/workbench.sh" extract handlers:declare --input "file=$ROOT/streams.yaml" --input uri=streams.yaml | show declare
      "$ROOT/scripts/workbench.sh" extract handlers:run | show run ;;
  run) "$ROOT/scripts/workbench.sh" extract handlers:run | show run ;;
  *) sed -n '2,6p' "$0"; exit 2 ;;
esac
