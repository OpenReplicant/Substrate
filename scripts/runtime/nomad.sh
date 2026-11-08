# Runtime: Nomad (S-16, S-17). A single-node agent on this machine (deploy/nomad/agent.hcl) runs the job
# deploy/nomad/substrate.nomad.hcl with the Podman or Docker task driver. Linux only.
# Sourced by scripts/lib.sh; defines rt_up, rt_down, rt_status, rt_logs.
# shellcheck shell=sh

NOMAD_ADDR=$(env_value NOMAD_ADDR); NOMAD_ADDR=${NOMAD_ADDR:-http://127.0.0.1:4646}
export NOMAD_ADDR
NOMAD_STATE="$ROOT/.state/nomad"

# A short image name means a registry image; the Podman driver wants it fully qualified.
qualify() {
  case "$1" in
    localhost/*|*.*/*|*:*/*) printf '%s' "$1" ;;      # already has a registry
    */*) printf 'docker.io/%s' "$1" ;;
    *) printf 'docker.io/library/%s' "$1" ;;
  esac
}

nomad_agent() {
  if nomad node status >/dev/null 2>&1; then return 0; fi
  command -v nomad >/dev/null 2>&1 || { echo "nomad is not installed (scripts/bootstrap.sh says how)" >&2; return 1; }
  mkdir -p "$NOMAD_STATE/data" "$NOMAD_STATE/plugins"
  extra=""
  if [ "$ENGINE" = podman ]; then
    socket="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/podman/podman.sock"
    [ "$(id -u)" = 0 ] && socket=/run/podman/podman.sock
    cat > "$NOMAD_STATE/podman.hcl" <<EOF
plugin "nomad-driver-podman" {
  config {
    socket_path = "unix://$socket"
    volumes {
      enabled = true
    }
  }
}
EOF
    extra="-config=$NOMAD_STATE/podman.hcl"
    [ -S "$socket" ] || echo "  note: no Podman socket at $socket (systemctl --user enable --now podman.socket)" >&2
  fi
  echo "  starting the Nomad agent (log: .state/nomad/agent.log)"
  # shellcheck disable=SC2086
  nohup nomad agent -config="$ROOT/deploy/nomad/agent.hcl" $extra \
    -data-dir="$NOMAD_STATE/data" -plugin-dir="$NOMAD_STATE/plugins" > "$NOMAD_STATE/agent.log" 2>&1 &
  echo $! > "$NOMAD_STATE/agent.pid"
  i=0
  until nomad node status 2>/dev/null | grep -q ready; do
    i=$((i + 1)); [ $i -gt 60 ] && { echo "the Nomad agent did not become ready: .state/nomad/agent.log" >&2; return 1; }
    sleep 2
  done
  echo "  Nomad agent ready at $NOMAD_ADDR"
}

# One Variable per group, holding only that group's secrets (read by the job's templates).
nomad_variables() {
  secrets_export || return 1   # from the secrets slot when they are not in .env (S-31)
  specs=$(python3 - "$ENV_FILE" <<'EOF'
import json, os, sys
env = {}
for line in open(sys.argv[1]).read().splitlines():
    k, sep, v = line.partition("=")
    if sep and not k.startswith("#"):
        env[k.strip()] = v.strip()
env.update({k: v for k, v in os.environ.items() if v})
groups = {"db": ["POSTGRES_PASSWORD"],
          "kernel": ["POSTGRES_PASSWORD", "KK_AUTHENTICATOR_PASSWORD", "KK_JWT_SECRET"],
          "gateway": ["BIFROST_VIRTUAL_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"],
          "map": ["BACKSTAGE_MCP_TOKEN"],
          "console": ["SUBSTRATE_BUS_PASSWORD"]}
for g, keys in groups.items():
    items = {k: env[k] for k in keys if env.get(k)}
    print(f"nomad/jobs/substrate/{g}\t" + json.dumps({"Items": items}))
EOF
) || return 1
  # values travel on stdin, never in argv
  printf '%s\n' "$specs" | while IFS='	' read -r path spec; do
    printf '%s' "$spec" | nomad var put -force -in=json "$path" - >/dev/null || exit 1
  done || return 1
  echo "  secrets written to Nomad Variables nomad/jobs/substrate/{db,kernel,gateway,map,console}"
}

rt_up() {
  nomad_agent || return 1
  nomad_variables || return 1
  mkdir -p "$ROOT/.state/data/postgres" "$ROOT/.state/data/bifrost" "$ROOT/.state/data/prometheus" "$ROOT/.state/artifacts" "$ROOT/.state/otel"
  chmod 777 "$ROOT/.state/data/bifrost" "$ROOT/.state/data/prometheus" "$ROOT/.state/otel"     # the images run as non-root users
  # what kk serve runs: KK_SERVE_PARTS if set, else substrate's compose default (S-33), so both runtimes match
  parts=$(env_value KK_SERVE_PARTS)
  [ -n "$parts" ] || parts=$(sed -n 's/.*KK_SERVE_PARTS:-\([^}]*\)}.*/\1/p' "$ROOT/deploy/compose.yaml" | head -1)
  prefix=""; [ "$ENGINE" = podman ] && prefix="localhost/"   # how each engine names a locally built image
  nomad job run -detach \
    -var "root=$ROOT" \
    -var "driver=$ENGINE" \
    -var "serve_parts=$parts" \
    -var "kernel_image=${prefix}knowledge-kernel:local" \
    -var "db_image=${prefix}knowledge-kernel-db:local" \
    -var "caddy_image=$(qualify "$(env_value FRONT_DOOR_IMAGE)")" \
    -var "bifrost_image=$(qualify "$(env_value BIFROST_IMAGE)")" \
    -var "prometheus_image=$(qualify "$(env_value PROMETHEUS_IMAGE)")" \
    -var "backstage_image=$(qualify "$(env_value BACKSTAGE_IMAGE)")" \
    -var "db_port=$(env_value KK_DB_PORT)" \
    -var "bifrost_port=$(env_value BIFROST_PORT)" \
    -var "backstage_port=$(env_value BACKSTAGE_PORT)" \
    -var "prometheus_port=$(env_value PROMETHEUS_PORT)" \
    -var "otel_image=$(qualify "$(env_value OTEL_COLLECTOR_IMAGE)")" \
    -var "otel_grpc_port=$(env_value OTEL_GRPC_PORT)" \
    -var "otel_http_port=$(env_value OTEL_HTTP_PORT)" \
    "$ROOT/deploy/nomad/substrate.nomad.hcl"
}

rt_down() {   # [--volumes] [--agent]
  nomad job stop -purge substrate 2>/dev/null || true
  for a in "$@"; do
    case "$a" in
      --volumes) rm -rf "$ROOT/.state/data" "$ROOT/.state/artifacts" ;;
      --agent) [ -f "$NOMAD_STATE/agent.pid" ] && kill "$(cat "$NOMAD_STATE/agent.pid")" 2>/dev/null; rm -f "$NOMAD_STATE/agent.pid" ;;
    esac
  done
}

rt_status() {
  nomad job status substrate
}

rt_logs() {   # TASK (postgres, init, kernel, caddy, console, bifrost, backstage, prometheus, otel-collector)
  nomad alloc logs -stderr -job substrate "$1"
  nomad alloc logs -job substrate "$1" | tail -200
}
