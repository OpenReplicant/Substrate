#!/bin/sh
# Bring up the whole stack and connect a project to kernel (default: this repository, S-10).
#
#   scripts/up.sh [PROJECT_DIR]
#
# Steps: .env (secrets generated once) -> the gateway's config -> images (kernel, Backstage if missing) ->
# every service -> wait until each answers -> kk up --no-stack (logins, MCP, skill, hooks, reading the project).
set -eu
. "$(dirname "$0")/lib.sh"

project=$(cd "${1:-$ROOT}" && pwd)
[ -d "$KERNEL/.git" ] || { echo "repos/kernel is missing: run scripts/bootstrap.sh" >&2; exit 1; }

say "Settings (.env)"
if [ ! -f "$ENV_FILE" ]; then cp "$ROOT/.env.example" "$ENV_FILE"; chmod 600 "$ENV_FILE"; echo "  created .env"; fi
python3 - "$ENV_FILE" <<'EOF'
import secrets, sys
path = sys.argv[1]
gen = {"POSTGRES_PASSWORD": lambda: secrets.token_urlsafe(24),
       "KK_AUTHENTICATOR_PASSWORD": lambda: secrets.token_urlsafe(24),
       "KK_JWT_SECRET": lambda: secrets.token_urlsafe(48),
       "BIFROST_VIRTUAL_KEY": lambda: "sk-bf-" + secrets.token_hex(24),
       "BACKSTAGE_MCP_TOKEN": lambda: secrets.token_urlsafe(32)}
lines, filled = open(path).read().splitlines(), []
for i, line in enumerate(lines):
    k, sep, v = line.partition("=")
    if sep and k in gen and not v.strip():
        lines[i] = f"{k}={gen[k]()}"; filled.append(k)
open(path, "w").write("\n".join(lines) + "\n")
print("  generated " + ", ".join(filled) if filled else "  secrets already set")
EOF
echo "  engine: $ENGINE"

say "Gateway config"
python3 "$ROOT/scripts/render_bifrost.py"

say "Images"
"$ENGINE" build -q -t knowledge-kernel:local "$KERNEL" >/dev/null && echo "  knowledge-kernel:local built"
bs_image=$(env_value BACKSTAGE_IMAGE); bs_image=${bs_image:-localhost/substrate-backstage:local}
if "$ENGINE" image inspect "$bs_image" >/dev/null 2>&1; then
  echo "  $bs_image present (rebuild with scripts/backstage-build.sh)"
else
  "$ROOT/scripts/backstage-build.sh"
fi

say "Services"
compose up -d

say "Waiting for each service"
wait_for() {   # name url
  i=0
  until curl -fsS -o /dev/null "$2" 2>/dev/null; do
    i=$((i + 1)); [ $i -gt 90 ] && { echo "  $1 did not answer at $2: $ENGINE compose ... logs" >&2; return 1; }
    sleep 2
  done
  echo "  $1 ok"
}
wait_for kernel "http://127.0.0.1:8080/ui/views.json"
wait_for gateway "http://127.0.0.1:$(env_value BIFROST_PORT)/health"
wait_for map "http://127.0.0.1:$(env_value BACKSTAGE_PORT)/.backstage/health/v1/readiness"

say "Kernel: logins and the project ($project)"
scan=""; command -v gitleaks >/dev/null 2>&1 || { scan="--no-scan"; echo "  gitleaks missing: connecting without reading the project"; }
KK_ADMIN_URL="postgresql://postgres:$(env_value POSTGRES_PASSWORD)@127.0.0.1:$(env_value KK_DB_PORT)/kk" \
KK_JWT_SECRET="$(env_value KK_JWT_SECRET)" \
  "$ROOT/.venv/bin/kk" up --no-stack $scan "$project"

say "Up"
"$ROOT/scripts/check.sh" || true
