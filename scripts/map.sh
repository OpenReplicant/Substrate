#!/bin/sh
# The map into kernel (kernel D-100, S-33): runs kernel's encoder-backstage on catalog-info.yaml inside the tools
# container, as the module's own agent. The catalog stays in Backstage's terms; kernel's mappings pack relates
# them to kk-tosca. Its three systems (core, options, sources; S-47) all become claims, so recall can answer what
# runs, what could be chosen and where to search.
# Safe to run any time: an unchanged file submits nothing, a changed one supersedes what the last version said.
# The PostToolUse hook in .claude/settings.json runs it after an edit to a catalog-info.yaml.
#
#   scripts/map.sh [PROJECT_DIR]      # default: this repository; reads PROJECT_DIR/catalog-info.yaml
#   scripts/map.sh --hook             # from the hook (the tool call's JSON on stdin): quiet, never fails the session
set -eu
. "$(dirname "$0")/lib.sh"

hook=""
if [ "${1:-}" = --hook ]; then
  hook=1; shift
  # only after an edit to a catalog file
  python3 -c 'import json, sys; p = (json.load(sys.stdin).get("tool_input") or {}).get("file_path") or ""; sys.exit(0 if p.endswith("catalog-info.yaml") else 1)' || exit 0
fi
project=$(cd "${1:-$ROOT}" && pwd)
catalog="$project/catalog-info.yaml"
[ -f "$catalog" ] || { [ -n "$hook" ] || echo "  no catalog-info.yaml in $project"; exit 0; }
"$ROOT/scripts/tools.sh" status >/dev/null 2>&1 || { [ -n "$hook" ] && exit 0; echo "  the tools container is not running: scripts/up.sh" >&2; exit 1; }

quiet() { if [ -n "$hook" ]; then "$@" >/dev/null 2>&1 || true; else "$@"; fi; }
secrets_export
quiet env DATABASE_URL="postgresql://kk_authenticator:$(env_value KK_AUTHENTICATOR_PASSWORD)@127.0.0.1:$(env_value KK_DB_PORT)/kk" \
  KK_ROLE=kkm_encoder_backstage \
  "$ROOT/bin/in-tools" python3 -m encoder_backstage --project "$(basename "$project")" --root "$project" \
  --artifacts "$ROOT/.state/artifacts" "$catalog"
