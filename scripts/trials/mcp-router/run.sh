#!/bin/sh
# The MCP router trial (S-204): each router in a container on the stack's network (it reaches the kernel as `kernel`),
# beside the decision service; run.py's cases from the host. Needs the stack up (scripts/up.sh). The kernel's secret
# goes to containers and run.py by name; the JWKS made from it is written mode 600 under .state and removed after.
#
#   scripts/trials/mcp-router/run.sh agentgateway|ours
set -eu
cd "$(dirname "$0")/../../.."
ENGINE=${CONTAINER_ENGINE:-podman}
KERNEL_IMAGE=ghcr.io/openreplicant/kernel:main   # its Python has PyJWT and cryptography, for the client
HERE=scripts/trials/mcp-router
STATE=.state/trials/mcp-router
NET=substrate_default
PY=docker.io/library/python:3.13.17-slim-bookworm
mkdir -p "$STATE"; umask 077
cleanup() { "$ENGINE" rm -f trial-decide trial-router trial-connector >/dev/null 2>&1 || true; rm -f "$STATE/jwks.json" "$STATE/ed25519.pem"; }
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
  ours)
    # Substrate's router (S-205) from the stack (scripts/up.sh): the trial's stdio tools join it through a connector
    # of their own, on the connectors' login; the kernel's connector is the stack's. Secrets go by name only.
    DATABASE_URL="postgresql://mcp_connector:$(sed -n 's/^MCP_CONNECTOR_DB_PASSWORD=//p' .env | tail -1)@db:5432/kernel"
    export DATABASE_URL
    KK_JWT_SECRET=$(sed -n 's/^KK_JWT_SECRET=//p' .env | tail -1); export KK_JWT_SECRET
    "$ENGINE" run -d --replace --name trial-connector --network "$NET" -e DATABASE_URL -v "$PWD/$HERE:/trial:ro,Z" \
      ghcr.io/openreplicant/substrate-mcp-router:main connect --name tools --stdio "python3 /trial/tools_server.py" >/dev/null
    sleep 4
    "$ENGINE" logs trial-connector > "$STATE/ours-connector.log" 2>&1 || true
    # the kernel's tools carry no annotations, so each starts behind `propose`; a person opens the one read tool the
    # cases use, as a person would (scripts/env.py gate)
    act=$("$ENGINE" exec substrate-db-1 psql -U postgres -d kernel -Atc "select actuator from env.mcp_tools() where name = 'kernel_recall'")
    [ -n "$act" ] && bin/in-tools python3 scripts/env.py gate "$act" free --as person_owner >/dev/null
    client() { "$ENGINE" run --rm --network=host --userns=keep-id --user "$(id -u):$(id -g)" -v "$PWD:/w:Z" -w /w \
      -e ROUTER=ours -e ROUTER_URL=http://127.0.0.1:8083/mcp -e KK_JWT_SECRET -e PHASE="$1" "$KERNEL_IMAGE" \
      python3 "$HERE/run_ours.py"; }
    client 1 || true
    "$ENGINE" restart substrate-mcp-router-1 >/dev/null    # a held call outlives the router: it is a row, not a request
    sleep 3
    client 2 || true
    "$ENGINE" logs trial-connector > "$STATE/ours-connector.log" 2>&1 || true
    # the trial's leftovers off the owner's page: its own waiting proposals refused (kept in the record), its server's
    # tools marked absent (its connector is gone)
    for a in $("$ENGINE" exec substrate-db-1 psql -U postgres -d kernel -Atc "select id from env.action where status = 'proposed' and actuator like 'mcp.%' and caller in ('person_owner', 'agent_claude_code') and input->>'server' = 'tools'"); do
      bin/in-tools python3 scripts/env.py decide "$a" no "trial clean-up (S-205)" --as trial >/dev/null || true
    done
    "$ENGINE" exec substrate-db-1 psql -U postgres -d kernel -qc "update env.mcp_tool set present = false where server = 'tools'"
    exit 0 ;;
  *) echo "unknown router $1" >&2; exit 2 ;;
esac
sleep 4
# the router's log goes to a file only: a router may echo its configuration, keys included (S-204 found one that did)
"$ENGINE" logs trial-router > "$STATE/$1.log" 2>&1 || true
"$ENGINE" run --rm --network=host --userns=keep-id --user "$(id -u):$(id -g)" -v "$PWD:/w:Z" -v "$PWD/$STATE:/state:Z" -w /w \
  -e ROUTER="$1" -e ROUTER_URL="$URL" -e DECIDE_URL=http://127.0.0.1:3901 -e TOKEN_ISS -e ED25519_KEY -e KK_JWT_SECRET \
  "$KERNEL_IMAGE" python3 "$HERE/run.py" || true
"$ENGINE" logs trial-router > "$STATE/$1.log" 2>&1 || true
