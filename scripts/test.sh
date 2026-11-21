#!/bin/sh
# Every test suite, in the tools container, each in a throwaway database it drops after (the stack must be up).
#
#   scripts/test.sh                 # all of them
#   scripts/test.sh FILE...         # some: scripts/tests/test_gateway.py, ...
#
# The tests that start a throwaway Knowledge Kernel (KERNEL_TESTS: the store's and the UI's, S-154) run in the kernel's
# image instead (scripts/build.sh kernel), on the host network, with this checkout mounted read-only: `kk`, its modules
# and the MCP server are there, and the tools container has none of them.
set -eu
. "$(dirname "$0")/lib.sh"

url="postgresql://postgres:$(env_value POSTGRES_PASSWORD)@127.0.0.1:$(env_value DB_PORT)/postgres"
[ $# -gt 0 ] || set -- "$ROOT"/scripts/tests/test_*.py
KERNEL_TESTS="scripts/tests/test_store.py scripts/tests/test_ui.py"
kimage=substrate-kernel:local; [ "$ENGINE" = podman ] && kimage=localhost/substrate-kernel:local
failed=0
for f in "$@"; do
  rel=${f#"$ROOT"/}
  case " $KERNEL_TESTS " in
    *" $rel "*) run() { "$ENGINE" run --rm --network host --cap-drop ALL --security-opt no-new-privileges --user "$(id -u):$(id -g)" \
                          -e PYTHONDONTWRITEBYTECODE=1 -e ADMIN_URL="$url" -v "$ROOT:$ROOT:ro" -w "$ROOT" "$kimage" python3 "$rel"; } ;;
    *) run() { "$ROOT/bin/in-tools" env ADMIN_URL="$url" python3 "$rel"; } ;;
  esac
  if out=$(cd "$ROOT" && run 2>&1); then
    printf '  ok    %s: %s\n' "$rel" "$(printf '%s\n' "$out" | tail -1)"
  else
    failed=$((failed + 1))
    printf '  FAIL  %s\n' "$rel"
    printf '%s\n' "$out" | grep -v '^ok ' | tail -12 | sed 's/^/        /'
  fi
done
[ $failed -eq 0 ] && echo "All test suites passed." || echo "$failed test suite(s) failed."
exit $failed
