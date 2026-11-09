#!/bin/sh
# Contract tests for the core interfaces (scripts/contract.py): what any filler of a slot must do. The map names
# each on its API (morphogen.dev/tests); results go to .state/contracts and, through substrate:contracts, into
# Workbench as claims (when the stack is up).
#
#   scripts/contract.sh INTERFACE [FILLER]   # e.g. secrets-api openbao
#   scripts/contract.sh all                  # every core interface with its current filler
set -u
here=$(dirname "$0")
python3 "$here/contract.py" "$@"
code=$?
if [ "$code" != 2 ] && curl -fsS -o /dev/null "http://127.0.0.1:8080/wb/api/health" 2>/dev/null; then
  "$here/workbench.sh" extract substrate:contracts 2>/dev/null | python3 -c 'import json, sys; d = json.load(sys.stdin); print("  substrate:contracts", "ok" if d.get("ok") else "FAILED: " + str(d.get("error")), *(d.get("log") or []))' || true
fi
exit "$code"
