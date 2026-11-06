#!/bin/sh
# Bring up the substrate for one project: kernel's stack and harness wiring (kk up), then the gateway and
# its Prometheus (deploy/compose.yaml). Needs Docker or Podman with compose, Python 3.12+, git.
#
#   scripts/up.sh ~/code/my-project
#
# Afterwards: harness/README.md (Claude Code through the gateway, Morphogen's plugin).
set -eu

project=${1:?usage: scripts/up.sh PROJECT_DIR}
root=$(cd "$(dirname "$0")/.." && pwd)
kernel="$root/vendor/kernel"

if [ ! -f "$kernel/pyproject.toml" ]; then
  git -C "$root" submodule update --init
fi

# kernel's own command; installs into whatever Python environment is active
command -v kk >/dev/null 2>&1 || pip install -e "$kernel"

# kernel's stack, the owner's and the agent's logins, MCP + skill + hooks merged into the project (kernel D-57)
kk up "$project"

# the gateway and Prometheus, in the same compose project as kernel's stack (S-06)
docker compose -f "$kernel/deploy/compose.yaml" -f "$root/deploy/compose.yaml" \
  --env-file "$kernel/deploy/.env" up -d bifrost prometheus

port=${BIFROST_PORT:-8090}
cat <<EOF

Substrate is up.
  Kernel UI:        http://127.0.0.1:8080/ui/   (sign-in printed by kk up above)
  Model gateway:    http://127.0.0.1:$port/     (add a provider and a virtual key on first start)
  Claude Code:      ANTHROPIC_BASE_URL=http://127.0.0.1:$port/anthropic   (harness/README.md)
  Judge:            in Claude Code, /plugin marketplace add OpenReplicant/Morphogen
                    then /plugin install morphogen@morphogen
EOF
