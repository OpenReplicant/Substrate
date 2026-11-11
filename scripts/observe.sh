#!/bin/sh
# Observe this system as it runs (plugins/substrate/OBSERVE.md): the collector reads the host, the container engine
# and what observe.yaml lists into snapshots in .state/observed/<host>/; gitleaks checks them for anything secret
# (a hit stops here, before Workbench reads them); substrate:observed turns them into items, substrate:drift
# compares them with the map, and substrate:reasoner draws what follows from the relations.
#
#   scripts/observe.sh            # collect, check, extract, drift
#   scripts/observe.sh --collect  # only the snapshots
set -eu
. "$(dirname "$0")/lib.sh"

CONTAINER_ENGINE=$ENGINE python3 "$ROOT/plugins/substrate/observe.py" "$ROOT" | sed 's/^/  /'
"$ROOT/bin/gitleaks" dir --no-banner --redact --exit-code 3 "$ROOT/.state/observed" >/dev/null 2>&1 || {
  code=$?
  [ "$code" = 3 ] && { echo "  gitleaks found something secret in .state/observed: not extracted (bin/gitleaks dir --redact .state/observed)" >&2; exit 1; }
  echo "  gitleaks did not run (exit $code): not extracted" >&2; exit 1
}
echo "  gitleaks: nothing secret in the snapshots"
[ "${1:-}" = --collect ] && exit 0
for x in observed drift reasoner; do
  "$ROOT/scripts/workbench.sh" extract "substrate:$x" | python3 -c 'import json, sys; d = json.load(sys.stdin); print("  substrate:'"$x"'", "ok" if d.get("ok") else "FAILED: " + str(d.get("error")), *(d.get("log") or [])); sys.exit(0 if d.get("ok") else 1)'
done
"$ROOT/scripts/streams.sh" run    # the gaps drift just raised, up their ladder (streams.yaml)
"$ROOT/scripts/recall.sh" || echo "  recall's vectors were not made (above); words and the graph still answer"
