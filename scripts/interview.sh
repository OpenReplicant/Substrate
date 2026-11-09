#!/bin/sh
# Interview transcripts into Workbench (plugins/substrate/INTERVIEW.md, the interview skill): gitleaks checks
# .state/interviews first (a hit stops here: people paste things), then substrate:interview records each statement
# that quotes the person word for word as their claim, and the map's relations, drift and inferences follow.
#
#   scripts/interview.sh
set -eu
. "$(dirname "$0")/lib.sh"

dir="$ROOT/.state/interviews"
[ -d "$dir" ] || { echo "  no transcripts yet (.state/interviews/<system>/<name>.md)"; exit 0; }
"$ROOT/bin/gitleaks" dir --no-banner --redact --exit-code 3 "$dir" >/dev/null 2>&1 || {
  code=$?
  [ "$code" = 3 ] && { echo "  gitleaks found something secret in .state/interviews: not read (bin/gitleaks dir --redact .state/interviews)" >&2; exit 1; }
  echo "  gitleaks did not run (exit $code): not read" >&2; exit 1
}
echo "  gitleaks: nothing secret in the transcripts"
"$ROOT/scripts/workbench.sh" extract substrate:interview | python3 -c 'import json, sys; d = json.load(sys.stdin); print("  substrate:interview", "ok" if d.get("ok") else "FAILED: " + str(d.get("error")), *(d.get("log") or [])); sys.exit(0 if d.get("ok") else 1)'
"$ROOT/scripts/map.sh"
