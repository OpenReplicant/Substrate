#!/bin/sh
# The MCP router trial (S-204): each router in a container on the stack's network (it reaches the kernel as `kernel`),
# beside the decision service; run.py's cases from the host. Needs the stack up (scripts/up.sh). The kernel's secret
# goes to containers and run.py by name; the JWKS made from it is written mode 600 under .state and removed after.
#
#   scripts/trials/mcp-router/run.sh agentgateway
set -eu
cd "$(dirname "$0")/../../.."
ENGINE=${CONTAINER_ENGINE:-podman}
KERNEL_IMAGE=ghcr.io/openreplicant/kernel:main   # its Python has PyJWT and cryptography, for the client
HERE=scripts/trials/mcp-router
STATE=.state/trials/mcp-router
NET=substrate_default
PY=docker.io/library/python:3.13.17-slim-bookworm
mkdir -p "$STATE"; umask 077
cleanup() { "$ENGINE" rm -f trial-decide trial-router >/dev/null 2>&1 || true; rm -f "$STATE/jwks.json" "$STATE/ed25519.pem"; }
trap cleanup EXIT
cleanup; trap cleanup EXIT
"$ENGINE" run -d --replace --name trial-decide --network "$NET" --network-alias decide -p 127.0.0.1:3901:9090 -v "$PWD/$HERE:/trial:ro,Z" "$PY" python3 /trial/decide.py >/dev/null
case "${1:?usage: run.sh agentgateway|bifrost}" in
  agentgateway)
    # it takes only asymmetric keys (RSA, EC, Ed25519; HS256 refused, S-204): an Ed25519 key made for this run
    "$ENGINE" run --rm --network=none --userns=keep-id --user "$(id -u):$(id -g)" -v "$PWD/$STATE:/out:Z" "$KERNEL_IMAGE" python3 -c '
import json, base64
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization as s
k = Ed25519PrivateKey.generate()
open("/out/ed25519.pem", "wb").write(k.private_bytes(s.Encoding.PEM, s.PrivateFormat.PKCS8, s.NoEncryption()))
x = base64.urlsafe_b64encode(k.public_key().public_bytes(s.Encoding.Raw, s.PublicFormat.Raw)).rstrip(b"=").decode()
open("/out/jwks.json", "w").write(json.dumps({"keys": [{"kty": "OKP", "crv": "Ed25519", "x": x, "alg": "EdDSA", "use": "sig", "kid": "kernel"}]}))'
    export ED25519_KEY=/state/ed25519.pem
    "$ENGINE" run -d --replace --name trial-router --network "$NET" -p 127.0.0.1:3900:3000 --userns=keep-id --user "$(id -u):$(id -g)" \
      -v "$PWD/$HERE:/trial:ro,Z" -v "$PWD/$STATE/jwks.json:/keys/jwks.json:ro,Z" \
      -v "$PWD/$HERE/agentgateway.yaml:/config.yaml:ro,Z" localhost/substrate-trial-agentgateway:1.7.0 -f /config.yaml >/dev/null
    URL=http://127.0.0.1:3900/mcp; export TOKEN_ISS=1 ;;
  *) echo "unknown router $1" >&2; exit 2 ;;
esac
sleep 4
# the router's log goes to a file only: a router may echo its configuration, keys included (S-204 found one that did)
"$ENGINE" logs trial-router > "$STATE/$1.log" 2>&1 || true
"$ENGINE" run --rm --network=host --userns=keep-id --user "$(id -u):$(id -g)" -v "$PWD:/w:Z" -v "$PWD/$STATE:/state:Z" -w /w \
  -e ROUTER="$1" -e ROUTER_URL="$URL" -e DECIDE_URL=http://127.0.0.1:3901 -e TOKEN_ISS -e ED25519_KEY -e KK_JWT_SECRET \
  "$KERNEL_IMAGE" python3 "$HERE/run.py" || true
"$ENGINE" logs trial-router > "$STATE/$1.log" 2>&1 || true
