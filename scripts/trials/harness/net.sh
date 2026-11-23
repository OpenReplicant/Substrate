#!/bin/sh
# The trial's network (S-172): internal (no route out), the stack's gateway attached as `gateway`, and a recording
# proxy (`proxy`, S-162's proxy_rec.py) that logs and refuses anything sent to it. A harness on this network reaches
# the gateway and nothing else: a call that honours HTTP(S)_PROXY is logged; one that does not, fails.
#   scripts/trials/harness/net.sh up|down
set -eu
here=$(cd "$(dirname "$0")" && pwd); root=$(cd "$here/../../.." && pwd)
out=$root/.state/trials/harness; mkdir -p "$out"
case "${1:-}" in
  up)
    podman network exists harness-trial || podman network create --internal harness-trial >/dev/null
    podman network connect --alias gateway harness-trial substrate-gateway-1 2>/dev/null || true
    podman rm -f harness-proxy >/dev/null 2>&1 || true
    podman run -d --name harness-proxy --network harness-trial --network-alias proxy --cap-drop ALL \
      -v "$root/scripts/trials/offline-agent:/p:ro" -v "$out:/out" -e PROXY_LOG=/out/proxy_hits.log \
      --entrypoint python3 docker.io/library/python:3.13-alpine -c \
      "import sys,runpy; sys.argv=['p','8888']; import http.server as h; exec(open('/p/proxy_rec.py').read().replace('\"127.0.0.1\"','\"0.0.0.0\"'))" >/dev/null
    echo "harness-trial up: gateway and proxy attached" ;;
  down)
    podman rm -f harness-proxy >/dev/null 2>&1 || true
    podman network disconnect harness-trial substrate-gateway-1 2>/dev/null || true
    podman network rm harness-trial >/dev/null 2>&1 || true
    echo "harness-trial down" ;;
  *) echo "usage: net.sh up|down" >&2; exit 2 ;;
esac
