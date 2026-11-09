#!/bin/sh
# Every test suite, in the tools container, each in a throwaway database it drops after (the stack must be up).
#
#   scripts/test.sh                 # all of them
#   scripts/test.sh FILE...         # some: workbench/tests/test_w1.py, plugins/substrate/tests/test_map.py, ...
set -eu
. "$(dirname "$0")/lib.sh"

url="postgresql://postgres:$(env_value POSTGRES_PASSWORD)@127.0.0.1:$(env_value DB_PORT)/postgres"
[ $# -gt 0 ] || set -- "$ROOT"/workbench/tests/test_*.py "$ROOT"/plugins/*/tests/test_*.py
failed=0
for f in "$@"; do
  rel=${f#"$ROOT"/}
  if out=$(cd "$ROOT" && "$ROOT/bin/in-tools" env WORKBENCH_ADMIN_URL="$url" python3 "$rel" 2>&1); then
    printf '  ok    %s: %s\n' "$rel" "$(printf '%s\n' "$out" | tail -1)"
  else
    failed=$((failed + 1))
    printf '  FAIL  %s\n' "$rel"
    printf '%s\n' "$out" | grep -v '^ok ' | tail -12 | sed 's/^/        /'
  fi
done
[ $failed -eq 0 ] && echo "All test suites passed." || echo "$failed test suite(s) failed."
exit $failed
