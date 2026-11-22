# Runtime: compose, the one runtime (S-41): deploy/compose.yaml, on Podman or Docker.
# Sourced by scripts/lib.sh; defines rt_up, rt_pull, rt_down, rt_status, rt_logs.
# shellcheck shell=sh

rt_up() {
  compose up -d --remove-orphans   # a service dropped from compose.yaml stops too
}

rt_pull() {   # IMAGE: fetch a published image; fails when it is not there (the caller then builds it)
  "$ENGINE" pull -q "$1" >/dev/null
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
