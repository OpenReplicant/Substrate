#!/bin/sh
# The secrets slot (S-31): SECRETS in .env names a backend in scripts/secrets/ (env, the default: .env itself;
# openbao: an OpenBao server on 127.0.0.1). Every script reads secrets through it (lib.sh's env_value).
#
#   scripts/secrets.sh start | stop | status
#   scripts/secrets.sh get NAME            # prints the value; use it in a pipe, not a terminal you share
#   scripts/secrets.sh put NAME            # the value on stdin
#   scripts/secrets.sh list                # the names (deploy/secrets.txt) and whether each is set
#   scripts/secrets.sh migrate             # with SECRETS=openbao: move the secrets in .env into OpenBao, blank them in .env
set -eu
. "$(dirname "$0")/lib.sh"

case "${1:-status}" in
  start) sec_start && echo "  secrets: $(sec_status)" ;;
  stop) sec_stop ;;
  status) echo "secrets: $SECRETS, $(sec_status)" ;;
  get) [ $# -eq 2 ] || { echo "usage: scripts/secrets.sh get NAME" >&2; exit 2; }; sec_get "$2" ;;
  put) [ $# -eq 2 ] || { echo "usage: scripts/secrets.sh put NAME < value" >&2; exit 2; }; sec_put "$2" ;;
  list)
    for name in $(secret_names); do
      if [ -n "$(sec_get "$name")" ]; then echo "  $name: set"; else echo "  $name: empty"; fi
    done ;;
  migrate)
    [ "$SECRETS" != env ] || { echo "SECRETS=env: secrets already live in .env; set SECRETS=openbao first" >&2; exit 1; }
    sec_start
    moved=""
    for name in $(secret_names); do
      v=$(env_file_value "$name")
      [ -n "$v" ] || continue
      printf '%s' "$v" | sec_put "$name"
      [ "$(sec_get "$name")" = "$v" ] || { echo "  $name did not read back; left in .env" >&2; continue; }
      printf '' | ( . "$ROOT/scripts/secrets/env.sh"; sec_put "$name" )
      moved="$moved $name"
    done
    echo "  moved into $SECRETS:${moved:- nothing}" ;;
  *) echo "usage: scripts/secrets.sh start|stop|status|get NAME|put NAME|list|migrate" >&2; exit 2 ;;
esac
