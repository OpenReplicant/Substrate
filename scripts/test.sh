#!/bin/sh
# Every test suite, in the tools container, each in a throwaway database it drops after (the stack must be up).
#
#   scripts/test.sh                 # all of them
#   scripts/test.sh FILE...         # some: scripts/tests/test_gateway.py, ..., or mcp-router (its Go tests)
#
# The tests that start a throwaway Knowledge Kernel (KERNEL_TESTS: the kernel's, the UI's and the review lane's, S-154, S-219) run in the kernel's
# image instead (published, or scripts/build.sh kernel), on the host network, with this checkout mounted read-only: `kk`, its modules
# and the MCP server are there, and the tools container has none of them.
set -eu
. "$(dirname "$0")/lib.sh"

url="postgresql://postgres:$(env_value POSTGRES_PASSWORD)@127.0.0.1:$(env_value DB_PORT)/postgres"
[ $# -gt 0 ] || set -- "$ROOT"/scripts/tests/test_*.py "$ROOT"/mcp-router
KERNEL_TESTS="scripts/tests/test_kernel.py scripts/tests/test_ui.py scripts/tests/test_review.py"
kimage=$(image_ref kernel)
# the kernel's login role is shared by the cluster: its fixture keeps the stack's password (passed by name, not value)
KK_AUTHENTICATOR_PASSWORD=$(env_value KK_AUTHENTICATOR_PASSWORD); export KK_AUTHENTICATOR_PASSWORD
failed=0
for f in "$@"; do
  rel=${f#"$ROOT"/}
  if [ "$rel" = mcp-router ]; then
    # the MCP router's Go tests (S-205), in the Go image its Containerfile builds with; modules cached in a volume
    gimage=$(sed -n 's/^FROM \(docker.io\/library\/golang:[^ ]*\) AS build$/\1/p' "$ROOT/mcp-router/Containerfile")
    run() { "$ENGINE" run --rm --cap-drop ALL --security-opt no-new-privileges -v substrate-go-cache:/go -e GOFLAGS=-mod=mod \
              -v "$ROOT/mcp-router:/src:ro" -w /src "$gimage" sh -c 'go vet ./... && go test -count=1 ./... 2>&1 | tail -3'; }
  else
  case " $KERNEL_TESTS " in
    *" $rel "*) run() { "$ENGINE" run --rm --network host --cap-drop ALL --security-opt no-new-privileges --user "$(id -u):$(id -g)" \
                          -e PYTHONDONTWRITEBYTECODE=1 -e KK_AUTHENTICATOR_PASSWORD -e ADMIN_URL="$url" -v "$ROOT:$ROOT:ro" -w "$ROOT" "$kimage" python3 "$rel"; } ;;
    *) run() { "$ROOT/bin/in-tools" env ADMIN_URL="$url" python3 "$rel"; } ;;
  esac
  fi
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
