#!/bin/sh
# Once per machine: check the tools, clone kernel and Morphogen into repos/ (full clones you can push from),
# and install their commands into .venv. Safe to run again: existing clones are left as they are.
#
#   scripts/bootstrap.sh
set -eu
. "$(dirname "$0")/lib.sh"

say "Tools"
missing=""
need() { command -v "$1" >/dev/null 2>&1 && printf '  %-10s %s\n' "$1" "$(command -v "$1")" || { printf '  %-10s MISSING (%s)\n' "$1" "$2"; missing="$missing $1"; }; }
need git "https://git-scm.com"
need python3 "3.12 or later"
need uv "Morphogen's tooling: https://docs.astral.sh/uv/"
need "$ENGINE" "CONTAINER_ENGINE in .env picks docker or podman"
echo "  runtime    $RUNTIME (RUNTIME in .env: compose or nomad)"
need node "22 or 24, for building Backstage"
need corepack "ships with Node; provides yarn"
need claude "Claude Code"
need gitleaks "kernel's ingest filter; without it kk up skips reading the project"
python3 -c 'import sys; sys.exit(sys.version_info < (3, 12))' || { echo "  python3 is older than 3.12"; missing="$missing python3"; }
if [ "$RUNTIME" = compose ]; then
  "$ENGINE" compose version >/dev/null 2>&1 && echo "  compose    $("$ENGINE" compose version 2>/dev/null | head -1)" \
    || { echo "  compose    MISSING ($ENGINE compose; with Podman, install docker-compose or podman-compose)"; missing="$missing compose"; }
fi
if [ "$RUNTIME" = nomad ] && [ "$(uname -s)" != Linux ]; then
  echo "  RUNTIME=nomad needs Linux (the Podman driver is Linux only, and host networking is used); use RUNTIME=compose here" >&2
  exit 1
fi
case "$missing" in
  *git*|*python3*|*uv*|*"$ENGINE"*|*compose*) echo "Install the missing tools above, then run this again." >&2; exit 1 ;;
esac

say "Upstream clones (repos.yaml)"
mkdir -p "$ROOT/repos"
clone() {   # name url branch
  if [ -d "$ROOT/repos/$1/.git" ]; then
    echo "  $1: present ($(git -C "$ROOT/repos/$1" rev-parse --abbrev-ref HEAD) at $(git -C "$ROOT/repos/$1" rev-parse --short HEAD))"
  else
    git clone --branch "$3" "$2" "$ROOT/repos/$1"
  fi
}
clone kernel "$(sed -n '/^kernel:/,/^[a-z]/s/^  url: //p' "$ROOT/repos.yaml")" main
clone morphogen "$(sed -n '/^morphogen:/,/^[a-z]/s/^  url: //p' "$ROOT/repos.yaml")" main

say "Commands"
[ -d "$ROOT/.venv" ] || python3 -m venv "$ROOT/.venv"
"$ROOT/.venv/bin/pip" install -q --upgrade pip
"$ROOT/.venv/bin/pip" install -q -e "$KERNEL"
echo "  kk:        $ROOT/.venv/bin/kk (editable: changes in repos/kernel apply at once)"
(cd "$MORPHOGEN" && uv sync -q)
echo "  morphogen: uv run --project repos/morphogen morphogen"

if [ "$RUNTIME" = nomad ]; then
  say "Nomad (pinned, checksums checked)"
  v=$(env_value NOMAD_VERSION); v=${v:-$(sed -n 's/^NOMAD_VERSION=//p' "$ROOT/.env.example")}
  python3 "$ROOT/scripts/install_hashicorp.py" nomad "$v" "$ROOT/.state/bin"
  if [ "$ENGINE" = podman ]; then
    v=$(env_value NOMAD_DRIVER_PODMAN_VERSION); v=${v:-$(sed -n 's/^NOMAD_DRIVER_PODMAN_VERSION=//p' "$ROOT/.env.example")}
    python3 "$ROOT/scripts/install_hashicorp.py" nomad-driver-podman "$v" "$ROOT/.state/nomad/plugins"
    systemctl --user is-active podman.socket >/dev/null 2>&1 || [ "$(id -u)" = 0 ] \
      || echo "  note: the Podman driver needs Podman's API socket: systemctl --user enable --now podman.socket"
  fi
fi

say "Done"
echo "Next: scripts/up.sh"
