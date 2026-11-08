#!/bin/sh
# Morphogen's verdicts into kernel (spec step 1, kernel D-99): runs kernel's encoder-morphogen module on a
# project's evidence log (<git common dir>/morphogen/evidence.db) inside the tools container, as the module's own
# agent. Safe to run any time: the log's hash chain is checked first, and verdicts already recorded are not
# submitted again. The PostToolUse hook in .claude/settings.json runs it after each Morphogen tool call.
#
#   scripts/verdicts.sh [PROJECT_DIR]      # default: this repository
#   scripts/verdicts.sh --hook             # from the hook: quiet, never fails the session
set -eu
. "$(dirname "$0")/lib.sh"

hook=""
[ "${1:-}" = --hook ] && { hook=1; shift; }
project=$(cd "${1:-$ROOT}" && pwd)
log="$(cd "$project" && git rev-parse --path-format=absolute --git-common-dir)/morphogen/evidence.db"

quiet() { if [ -n "$hook" ]; then "$@" >/dev/null 2>&1 || true; else "$@"; fi; }
if [ ! -f "$log" ]; then
  [ -n "$hook" ] || echo "  no Morphogen evidence log yet at $log (nothing has been judged in $project)"
  exit 0
fi
"$ROOT/scripts/tools.sh" status >/dev/null 2>&1 || { [ -n "$hook" ] && exit 0; echo "  the tools container is not running: scripts/up.sh" >&2; exit 1; }

secrets_export
quiet env DATABASE_URL="postgresql://kk_authenticator:$(env_value KK_AUTHENTICATOR_PASSWORD)@127.0.0.1:$(env_value KK_DB_PORT)/kk" \
  KK_ROLE=kkm_encoder_morphogen \
  "$ROOT/bin/in-tools" python3 -m encoder_morphogen --project "$(basename "$project")" \
  --artifacts "$ROOT/.state/artifacts" "$log"
