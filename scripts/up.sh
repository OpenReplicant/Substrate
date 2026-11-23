#!/bin/sh
# Bring up the stack on the fresh tree (S-137): Postgres, the model gateway, local models, the UI (S-140), the
# tools container; then the substrate database (the environment's schema), the Knowledge Kernel's (S-154) and the gateway's.
#
#   scripts/up.sh
set -eu
. "$(dirname "$0")/lib.sh"

"$ROOT/scripts/settings.sh"
"$ROOT/scripts/build.sh"
say "The model gateway's config (scripts/gateway.py: providers from .env, a key per caller)"
python3 "$ROOT/scripts/gateway.py" render

say "Services ($RUNTIME)"
rt_up
"$ROOT/scripts/tools.sh" start

say "Databases"
"$ROOT/bin/in-tools" python3 "$ROOT/scripts/db.py" init        # waits for Postgres; stops at once on a refused password
"$ROOT/bin/in-tools" python3 "$ROOT/scripts/gateway.py" init   # its database and logins
"$ROOT/bin/in-tools" python3 "$ROOT/scripts/gateway.py" prune  # limits its store kept that config.json dropped (S-87)

say "The Knowledge Kernel (S-154)"
"$ROOT/scripts/kernel.sh" init       # its schema and default modules in the `kernel` database (the kernel service then applies change sets)

say "Up"
"$ROOT/scripts/check.sh"
