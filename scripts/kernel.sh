#!/bin/sh
# The Knowledge Kernel beside the store (S-153, S-154): its schema, the one-off export of the `store` schema into it,
# an agent's login, and the MCP server Claude Code starts. The kernel runs in its own image (scripts/build.sh kernel)
# in the stack's Postgres, database `kernel` (scripts/db.py init makes it); nothing is installed on the host.
#
#   scripts/kernel.sh init               # install the kernel's schema and default modules (safe to run again)
#   scripts/kernel.sh export             # the store's items and statements as kernel change sets (safe to run again:
#                                        # an unchanged item submits nothing); the kernel service applies them
#   scripts/kernel.sh login NAME         # an agent's own login (printed nowhere: .state/kernel/NAME.env, mode 600) and
#                                        # its MCP entry `kernel` in .mcp.json (the profile substrate: nine tools)
#   scripts/kernel.sh mcp NAME           # the stdio MCP server for that login (what .mcp.json runs)
set -eu
. "$(dirname "$0")/lib.sh"

image() { if [ "$ENGINE" = podman ]; then echo localhost/substrate-kernel:local; else echo substrate-kernel:local; fi; }

case "${1:-}" in
  init)
    compose run --rm kernel-init
    ;;
  export)
    compose run --rm kernel-export
    ;;
  login)
    name=${2:?usage: scripts/kernel.sh login NAME}
    mkdir -p "$ROOT/.state/kernel"
    out=$(compose run --rm -T kernel-init kk agent add "$name" | grep '^{' | tail -1)
    printf '%s' "$out" | python3 -c '
import json, os, sys
root, name, port = sys.argv[1:4]
out = json.load(sys.stdin)
path = os.path.join(root, ".state/kernel", name + ".env")
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f:
    f.write("KK_DATABASE_URL=postgresql://%s:%s@127.0.0.1:%s/kernel\n" % (out["role"], out["password"], port or "5432"))
mcp = os.path.join(root, ".mcp.json")
cfg = json.load(open(mcp)) if os.path.exists(mcp) else {}
cfg.setdefault("mcpServers", {})["kernel"] = {"command": os.path.join(root, "scripts/kernel.sh"), "args": ["mcp", name]}
open(mcp, "w").write(json.dumps(cfg, indent=2) + "\n")
print("  login %s: .state/kernel/%s.env; .mcp.json has the `kernel` server (tools mcp__kernel__*)" % (out["role"], name))
' "$ROOT" "$name" "$(env_value DB_PORT)"
    ;;
  mcp)
    name=${2:?usage: scripts/kernel.sh mcp NAME}
    login="$ROOT/.state/kernel/$name.env"
    [ -f "$login" ] || { echo "no login for $name: scripts/kernel.sh login $name" >&2; exit 1; }
    set -- -i --rm --network host --read-only --cap-drop ALL --security-opt no-new-privileges --user "$(id -u):$(id -g)" \
      -e KK_LOGIN_FILE=/login -e KK_PROFILE=substrate -v "$login:/login:ro"
    if [ "$ENGINE" = podman ] && [ "$(id -u)" != 0 ]; then set -- "$@" --userns keep-id; fi
    exec "$ENGINE" run "$@" "$(image)" kernel-mcp
    ;;
  *)
    sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//' >&2
    exit 2
    ;;
esac
