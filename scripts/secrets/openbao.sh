# The `openbao` secrets backend (S-31): OpenBao in a container on 127.0.0.1:8200, outside the runtime, so
# secrets are there before anything else starts (deploy/openbao/config.hcl). Its unseal key and the scripts'
# login live in .state/openbao/keys (mode 600); its data in .state/openbao/data. Reads and writes go through
# scripts/secrets/bao.py (standard library; values on stdin and stdout, never in argv).
# shellcheck shell=sh

BAO_DIR="$ROOT/.state/openbao"
BAO_NAME=substrate-openbao

bao_running() { [ "$("$ENGINE" inspect -f '{{.State.Running}}' "$BAO_NAME" 2>/dev/null)" = "true" ]; }

sec_start() {
  mkdir -p "$BAO_DIR/keys" "$BAO_DIR/data"
  chmod 700 "$BAO_DIR" "$BAO_DIR/keys"
  # first start: the static unseal key (32 bytes, AES-256) and the scripts' password
  [ -s "$BAO_DIR/keys/unseal.key" ] || python3 -c "import secrets,sys; sys.stdout.buffer.write(secrets.token_bytes(32))" > "$BAO_DIR/keys/unseal.key"
  [ -s "$BAO_DIR/keys/scripts.pw" ] || python3 -c "import secrets; print(secrets.token_urlsafe(32), end='')" > "$BAO_DIR/keys/scripts.pw"
  chmod 600 "$BAO_DIR/keys/unseal.key" "$BAO_DIR/keys/scripts.pw"
  if ! bao_running; then
    "$ENGINE" rm -f "$BAO_NAME" >/dev/null 2>&1 || true
    image=$(env_value OPENBAO_IMAGE); image=${image:-docker.io/openbao/openbao:2.7.1}
    set -- --detach --name "$BAO_NAME" --network host --cap-drop ALL --security-opt no-new-privileges \
      --user "$(id -u):$(id -g)" -e SKIP_CHOWN=1 \
      -v "$ROOT/deploy/openbao/config.hcl:/openbao/config/config.hcl:ro" \
      -v "$BAO_DIR/keys:/openbao/keys:ro" -v "$BAO_DIR/data:/openbao/data"
    if [ "$ENGINE" = podman ] && [ "$(id -u)" != 0 ]; then set -- "$@" --userns keep-id; fi
    "$ENGINE" run "$@" "$image" bao server -config=/openbao/config/config.hcl >/dev/null
  fi
  python3 "$ROOT/scripts/secrets/bao.py" wait || { echo "  OpenBao did not unseal: $ENGINE logs $BAO_NAME" >&2; return 1; }
}
sec_stop() { "$ENGINE" rm -f "$BAO_NAME" >/dev/null 2>&1 || true; }
sec_get() { python3 "$ROOT/scripts/secrets/bao.py" get "$1"; }
sec_put() { python3 "$ROOT/scripts/secrets/bao.py" put "$1"; }
sec_status() { python3 "$ROOT/scripts/secrets/bao.py" status; }
