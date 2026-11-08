#!/bin/sh
# .env from .env.example (new settings appended), and every generated secret in deploy/secrets.txt made once,
# in the secrets slot. Run by scripts/bootstrap.sh (compose needs the secrets even to build) and scripts/up.sh.
# Safe to run again: it only fills what is missing.
#
#   scripts/settings.sh
set -eu
. "$(dirname "$0")/lib.sh"

say "Settings (.env)"
if [ ! -f "$ENV_FILE" ]; then cp "$ROOT/.env.example" "$ENV_FILE"; chmod 600 "$ENV_FILE"; echo "  created .env"; fi
python3 - "$ENV_FILE" "$ROOT/.env.example" <<'EOF'
import secrets, sys
path, example = sys.argv[1], sys.argv[2]
lines = open(path).read().splitlines()
# settings added to .env.example since this .env was made: append them with their defaults
have = {l.partition("=")[0] for l in lines if "=" in l and not l.startswith("#")}
added = [l for l in open(example).read().splitlines() if "=" in l and not l.startswith("#") and l.partition("=")[0] not in have]
if added:
    lines += ["", "# added from .env.example by scripts/up.sh"] + added
    print("  added new settings: " + ", ".join(l.partition("=")[0] for l in added))
open(path, "w").write("\n".join(lines) + "\n")
EOF
echo "  runtime: $RUNTIME, engine: $ENGINE, secrets: $SECRETS"

say "Secrets ($SECRETS)"
sec_start
made=""
while read -r name kind _; do
  case "$name" in ''|'#'*) continue ;; esac
  [ "$kind" = provided ] && continue
  [ -n "$(env_value "$name")" ] && continue
  python3 -c "
import secrets, sys
kind = sys.argv[1].split(':')
out = secrets.token_urlsafe(int(kind[1])) if kind[0] == 'token' else kind[1] + secrets.token_hex(int(kind[2]))
sys.stdout.write(out)" "$kind" | sec_put "$name"
  made="$made $name"
done < "$ROOT/deploy/secrets.txt"
echo "  ${made:+generated$made; }$(sec_status)"
