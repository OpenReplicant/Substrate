#!/bin/sh
# The Knowledge Kernel (S-153, S-154): its schema, Substrate's catalog in it, an agent's login, and the MCP server Claude Code starts. The kernel runs in its own image (published, or scripts/build.sh kernel)
# in the stack's Postgres, database `kernel` (scripts/db.py init makes it); nothing is installed on the host.
#
#   scripts/kernel.sh init               # install the kernel's schema and default modules, then Substrate's kernel modules
#                                        # (environment/, by kk module install, S-219); safe to run again
#   scripts/kernel.sh catalog            # catalog/*.yaml (Substrate's parts, Backstage entities) into the kernel by
#                                        # encoder-backstage (S-176); an unchanged file submits nothing
#   scripts/kernel.sh login NAME         # an agent's own login (printed nowhere: .state/kernel/NAME.env, mode 600) and
#                                        # its MCP entry `kernel` in .mcp.json (the profile substrate: ten tools)
#   scripts/kernel.sh login NAME --no-mcp-json   # the same, without touching .mcp.json (for a service's own login)
#   scripts/kernel.sh mcp NAME           # the stdio MCP server for that login (what .mcp.json runs)
#   scripts/kernel.sh person NAME        # a person's sign-in for the shell at the front door (S-199): a reviewer; the
#                                        # password printed nowhere, kept in .state/kernel/person-NAME.password (mode 600);
#                                        # run again for a new password
set -eu
. "$(dirname "$0")/lib.sh"
# --no-deps: these need db up, not restarted. Without it, Podman's compose recreated db on every run, which restarted
# Postgres and left the gateway unable to resolve `db` (first deploy, 2026-11-21, S-155). scripts/up.sh starts db first.

image() { image_ref kernel; }

case "${1:-}" in
  init)
    compose run --rm --no-deps kernel-init
    # Substrate's kernel modules, through the kernel's module contract (S-219): the manifest checked, its migration applied
    # once; the module's service (compose `environment`) acts as the kernel's login switched to its role, so the login
    # kk module install writes for it is not used (written to the container's /tmp and gone with it)
    compose run --rm --no-deps -T kernel-init kk module install /substrate/environment --out /tmp/modules | grep '^{' | tail -1 |
      python3 -c 'import json, sys; r = json.load(sys.stdin); print("  module %s %s: migration %s" % (r["module"], r["version"], r["migration"]))'
    ;;
  catalog)
    compose run --rm --no-deps kernel-catalog
    ;;
  login)
    name=${2:?usage: scripts/kernel.sh login NAME [--no-mcp-json]}
    nomcp=${3:-}
    mkdir -p "$ROOT/.state/kernel"
    out=$(compose run --rm --no-deps -T kernel-init kk agent add "$name" | grep '^{' | tail -1)
    printf '%s' "$out" | python3 -c '
import json, os, sys
root, name, port, nomcp = sys.argv[1:5]
out = json.load(sys.stdin)
path = os.path.join(root, ".state/kernel", name + ".env")
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f:
    f.write("KK_DATABASE_URL=postgresql://%s:%s@127.0.0.1:%s/kernel\n" % (out["role"], out["password"], port or "5432"))
if nomcp:
    print("  login %s: .state/kernel/%s.env" % (out["role"], name))
    sys.exit(0)
mcp = os.path.join(root, ".mcp.json")
cfg = json.load(open(mcp)) if os.path.exists(mcp) else {}
cfg.setdefault("mcpServers", {})["kernel"] = {"command": os.path.join(root, "scripts/kernel.sh"), "args": ["mcp", name]}
open(mcp, "w").write(json.dumps(cfg, indent=2) + "\n")
print("  login %s: .state/kernel/%s.env; .mcp.json has the `kernel` server (tools mcp__kernel__*)" % (out["role"], name))
' "$ROOT" "$name" "$(env_value DB_PORT)" "$nomcp"
    ;;
  person)
    name=${2:?usage: scripts/kernel.sh person NAME}
    port=$(env_value DESKTOP_PORT); port=${port:-8080}
    mkdir -p "$ROOT/.state/kernel"
    out=$(compose run --rm --no-deps -T kernel-init kk person add "$name" | grep '^{' | tail -1)
    printf '%s' "$out" | python3 -c '
import json, os, sys
root, name, port = sys.argv[1:4]
out = json.load(sys.stdin)
path = os.path.join(root, ".state/kernel", "person-" + name + ".password")
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f:
    f.write(out["password"] + "\n")
print("  %s signs in at http://127.0.0.1:%s/ui/ as %s, with the password in .state/kernel/person-%s.password" % (out["role"], port, name, name))
' "$ROOT" "$name" "$port"
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
    sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//' >&2
    exit 2
    ;;
esac
