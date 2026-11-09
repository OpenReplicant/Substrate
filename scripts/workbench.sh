#!/bin/sh
# Workbench's command (workbench/workbench/cli.py), in the tools container, with its settings from .env.
#
#   scripts/workbench.sh migrate
#   scripts/workbench.sh plugin load plugins/substrate
#   scripts/workbench.sh user add NAME [--role owner|editor|viewer]   # prints the password once: run it yourself
#   scripts/workbench.sh user reset NAME | user list
#   scripts/workbench.sh extract substrate:catalog          # run an extractor now (it reads this checkout)
set -eu
. "$(dirname "$0")/lib.sh"

secrets_export
exec "$ROOT/bin/in-tools" env PYTHONPATH="$ROOT/workbench" \
  WORKBENCH_ADMIN_URL="postgresql://postgres:$(env_value POSTGRES_PASSWORD)@127.0.0.1:$(env_value KK_DB_PORT)/postgres" \
  WORKBENCH_AUTHENTICATOR_PASSWORD="$(env_value WORKBENCH_AUTHENTICATOR_PASSWORD)" \
  WORKBENCH_JWT_SECRET="$(env_value WORKBENCH_JWT_SECRET)" \
  WORKBENCH_SERVER_PASSWORD="$(env_value WORKBENCH_SERVER_PASSWORD)" \
  WORKBENCH_READER_PASSWORD="$(env_value WORKBENCH_READER_PASSWORD)" \
  WB_PLUGINS_DIR="$ROOT/plugins" \
  python3 -m workbench "$@"
