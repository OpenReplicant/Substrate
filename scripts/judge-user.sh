#!/bin/sh
# The judge under another Unix user (S-121; Morphogen's README, "A judge the author cannot reach"): its own
# Morphogen, its own clone of this repository, and the one command this user may run as it. Run by the owner in
# a terminal (it asks for the sudo password); never by an agent, which has no password to give.
#
#   scripts/judge-user.sh install COMMIT      # Morphogen at that commit of OpenReplicant/Morphogen, in the judge's venv
#   scripts/judge-user.sh clone [BRANCH]      # the judge's clone of this repository at BRANCH (default: the current one)
#   scripts/judge-user.sh door                # /usr/local/bin/morphogen-intake and the sudoers rule that allows it
#   scripts/judge-user.sh images IMAGE...     # copy images from this user's store to the judge's (Podman only)
#   scripts/judge-user.sh advance NAME [BRANCH]   # move the judge's base forward to BRANCH: the owner's, by password
#   scripts/judge-user.sh status              # what is in place (no password needed for what this user may see)
#
# The author's side then runs, with no password:
#   git bundle create - CANDIDATE ^BASE | sudo -u morphogen-judge /usr/local/bin/morphogen-intake NAME
set -eu
. "$(dirname "$0")/lib.sh"

JUDGE=${JUDGE_USER:-morphogen-judge}
HOME_J=$(getent passwd "$JUDGE" | cut -d: -f6)
[ -n "$HOME_J" ] || { echo "no user $JUDGE: sudo useradd --create-home --home-dir /var/lib/$JUDGE --shell /usr/sbin/nologin $JUDGE" >&2; exit 1; }
DOOR=/usr/local/bin/morphogen-intake
RULE=/etc/sudoers.d/morphogen-judge
SLUG=substrate

# run a shell line as the judge, in its home, with its own runtime directory (rootless Podman needs it)
as_judge() { sudo -u "$JUDGE" -H env "XDG_RUNTIME_DIR=/run/user/$(id -u "$JUDGE")" sh -c "cd ~ && $1"; }

case "${1:-status}" in
install)
  commit=${2:?usage: scripts/judge-user.sh install COMMIT}
  case "$commit" in *[!0-9a-f]*) echo "COMMIT is a full commit id" >&2; exit 1 ;; esac
  say "Morphogen $commit in $HOME_J/venv"
  as_judge "python3 -m venv venv && venv/bin/pip install --quiet --upgrade 'git+https://github.com/OpenReplicant/Morphogen@$commit' && venv/bin/morphogen --help >/dev/null && mkdir -p requests private projects && chmod 700 requests private && echo installed"
  ;;
clone)
  branch=${2:-$(git -C "$ROOT" branch --show-current)}
  say "the judge's clone of $ROOT at $branch"
  git -C "$ROOT" bundle create - "$branch" |
    as_judge "test ! -e projects/$SLUG || { echo 'projects/$SLUG exists: use advance' >&2; exit 1; }; mkdir -p projects && cat > base.bundle && git clone -q -b '$branch' base.bundle projects/$SLUG && rm base.bundle && git -C projects/$SLUG remote remove origin && git -C projects/$SLUG log --oneline -1"
  ;;
door)
  say "$DOOR and $RULE"
  tmp=$(mktemp -d)
  cat > "$tmp/door" <<EOF
#!/bin/sh
# The one command $(id -un) may run as $JUDGE (scripts/judge-user.sh door): judge the candidate bundled on
# standard input by the request the judge keeps under the name given. Owned by root.
cd $HOME_J || exit 2
HOME=$HOME_J XDG_RUNTIME_DIR=/run/user/\$(id -u) PATH=/usr/local/bin:/usr/bin:/bin
export HOME XDG_RUNTIME_DIR PATH
exec $HOME_J/venv/bin/morphogen intake judge "\$1"
EOF
  # sudo 1.9.10 and later take a regular expression for the arguments: one name, nothing else
  printf '%s ALL=(%s) NOPASSWD: %s ^[a-z0-9][a-z0-9-]*$\n' "$(id -un)" "$JUDGE" "$DOOR" > "$tmp/rule"
  sudo visudo -cf "$tmp/rule"
  sudo install -o root -g root -m 755 "$tmp/door" "$DOOR"
  sudo install -o root -g root -m 440 "$tmp/rule" "$RULE"
  rm -rf "$tmp"
  echo "in place"
  ;;
images)
  shift
  [ $# -gt 0 ] || { echo "usage: scripts/judge-user.sh images IMAGE..." >&2; exit 1; }
  for image in "$@"; do
    say "$image into the judge's store"
    podman save "$image" | as_judge "podman load"
  done
  ;;
advance)
  name=${2:?usage: scripts/judge-user.sh advance NAME [BRANCH]}
  branch=${3:-$(git -C "$ROOT" branch --show-current)}
  say "the judge's base for $name forward to $branch"
  git -C "$ROOT" bundle create - "$branch" | as_judge "venv/bin/morphogen intake advance '$name'"
  ;;
status)
  say "The judge user"
  echo "user $JUDGE, home $HOME_J ($(stat -c '%U %a' "$HOME_J"))"
  [ -x "$DOOR" ] && echo "door $DOOR ($(stat -c '%U %a' "$DOOR"))" || echo "no door yet: scripts/judge-user.sh door"
  if sudo -n -l -U "$(id -un)" "$DOOR" probe >/dev/null 2>&1; then echo "this user may run the door as $JUDGE without a password"
  else echo "this user may not run the door without a password (yet)"; fi
  ;;
*)
  sed -n '2,13p' "$0" >&2; exit 1 ;;
esac
