#!/bin/sh
# The companion's session (plan step 4, S-136), in its own container (compose service `companion`).
#
#   scripts/companion.sh login      # once: attach, then type /login in the session and follow the link
#   scripts/companion.sh attach     # see the session; detach with ctrl-b d (it keeps running)
#   scripts/companion.sh restart    # a fresh session (the channel's warning asks again)
#   scripts/companion.sh status
set -eu
. "$(dirname "$0")/lib.sh"

attach() { compose exec companion tmux attach -t companion; }

case "${1:-status}" in
  login)
    cat <<'TXT'
In the session that opens: type /login, pick your Claude account, open the link in your browser and paste the code
back. Then, if it asks, confirm "I am using this for local development" (the channel is Substrate's own server).
Detach with ctrl-b d; the session keeps running. The login stays in the companion's own volume.
TXT
    printf 'Press Enter to attach... '; read -r _
    attach ;;
  attach) attach ;;
  restart) compose restart companion; echo "  companion restarted: scripts/companion.sh attach to confirm the channel's warning" ;;
  status) compose exec -T companion tmux capture-pane -p -t companion | grep -v '^[[:space:]]*$' | tail -15 ;;
  *) echo "usage: scripts/companion.sh login|attach|restart|status" >&2; exit 1 ;;
esac
