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
"$ROOT/scripts/kernel.sh" export     # the store's items as change sets; an unchanged item submits nothing

[ -s "$ROOT/.state/kernel/worker.env" ] || "$ROOT/scripts/kernel.sh" login worker --no-mcp-json   # the worker's own login (memory profile)
# the worker reads it from .env (WORKER_KERNEL_URL), not a mounted file; once copied, its container is recreated with it
if [ -z "$(env_value WORKER_KERNEL_URL)" ]; then
  sec_start
  sed -n 's/^KK_DATABASE_URL=//p' "$ROOT/.state/kernel/worker.env" | tr -d '\n' | sec_put WORKER_KERNEL_URL
  echo "  the worker's kernel login: in .env (WORKER_KERNEL_URL)"
  rt_up
fi

say "Up"
"$ROOT/scripts/check.sh"
