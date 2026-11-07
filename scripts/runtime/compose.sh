# Runtime: compose (S-16). Kernel's compose project plus deploy/compose.yaml, on Docker or Podman.
# Sourced by scripts/lib.sh; defines rt_up, rt_down, rt_status, rt_logs.
# shellcheck shell=sh

rt_up() {
  compose up -d
}

rt_down() {   # [--volumes]
  compose down "$@"
}

rt_status() {
  compose ps
}

rt_logs() {   # SERVICE
  compose logs --tail 200 "$1"
}
