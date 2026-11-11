#!/bin/sh
# A business's map and its BPMN processes, in and out of Workbench (plugins/business/README.md):
#
#   scripts/business.sh import FILE.yaml             # a map file: its domain's items and relations (business:map)
#   scripts/business.sh import FILE.bpmn DOMAIN      # a BPMN 2.0 process into a business's domain (business:bpmn)
#   scripts/business.sh export-map DOMAIN            # the domain's map file, to stdout
#   scripts/business.sh export-bpmn PROCESS-SLUG     # a process as BPMN 2.0 XML with its diagram, to stdout
#   scripts/business.sh demo                         # the demo business (plugins/business/demo) into Workbench
set -eu
. "$(dirname "$0")/lib.sh"

abs() { case "$1" in /*) echo "$1" ;; *) echo "$PWD/$1" ;; esac; }
show() { python3 -c 'import json, sys; d = json.load(sys.stdin); print("  business:", "; ".join(d.get("log") or []) if d.get("ok") else d.get("error"))'; }
import_one() {
  f=$(abs "$1")
  case "$f" in
    *.bpmn) [ $# -ge 2 ] || { echo "a BPMN file needs the DOMAIN it belongs to" >&2; exit 2; }
            "$ROOT/scripts/workbench.sh" extract business:bpmn --input "file=$f" --input "domain=$2" --input "uri=${f#"$ROOT"/}" | show ;;
    *)      "$ROOT/scripts/workbench.sh" extract business:map --input "file=$f" --input "uri=${f#"$ROOT"/}" | show ;;
  esac
}
export_() {
  exec "$ROOT/bin/in-tools" env PYTHONPATH="$ROOT/workbench" \
    WORKBENCH_ADMIN_URL="postgresql://postgres:$(env_value POSTGRES_PASSWORD)@127.0.0.1:$(env_value DB_PORT)/postgres" \
    python3 "$ROOT/plugins/business/business_plugin.py" "$@"
}
case "${1:-}" in
  import) shift; import_one "$@" ;;
  export-map|export-bpmn) export_ "$@" ;;
  demo)
    import_one "$ROOT/plugins/business/demo/harbour-bakery.yaml"
    import_one "$ROOT/plugins/business/demo/wholesale-order.bpmn" harbour-bakery ;;
  *) sed -n '2,8p' "$0" >&2; exit 2 ;;
esac
