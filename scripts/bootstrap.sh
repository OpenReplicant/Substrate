#!/bin/sh
# Once per machine: check the few host tools and build every image (the upstream skill clones repos.yaml
# projects when one is worked on). Everything else (Python packages, gitleaks, uv) lives in containers (S-19). Safe to run again: existing clones are left as they are.
#
#   scripts/bootstrap.sh
set -eu
. "$(dirname "$0")/lib.sh"

say "Host tools"
required_missing=""
have() { command -v "$1" >/dev/null 2>&1; }
show() { if have "$1"; then printf '  %-10s %s\n' "$1" "$(command -v "$1")"; else printf '  %-10s missing: %s\n' "$1" "$2"; fi; }
require() { show "$1" "$2"; have "$1" || required_missing="$required_missing $1"; }

require git "https://git-scm.com"
require python3 "any Python 3.9+; the scripts use only its standard library"
require "$ENGINE" "CONTAINER_ENGINE in .env picks podman or docker"
if "$ENGINE" compose version >/dev/null 2>&1; then
  printf '  %-10s %s\n' compose "$("$ENGINE" compose version 2>/dev/null | head -1)"
else
  printf '  %-10s missing: %s compose (with Podman: the docker-compose provider, or podman-compose)\n' compose "$ENGINE"
  required_missing="$required_missing compose"
fi
show claude "Claude Code, to work in this repository (not needed to run the stack)"
if [ -n "$required_missing" ]; then
  echo "Install:$required_missing, then run this again." >&2
  exit 1
fi

"$ROOT/scripts/settings.sh"
"$ROOT/scripts/build.sh"

say "Tools container"
"$ROOT/scripts/tools.sh" start
echo "  bin/gitleaks and the scripts' Python now run inside it"

say "Done"
echo "Next: scripts/up.sh"
