# OpenBao, the `openbao` choice of the secrets slot (S-31). One server on 127.0.0.1, started by scripts/secrets.sh
# outside the runtime, so both runtimes (and every script) can read secrets before anything else starts.
#
# Unsealing: a static key (the "static" seal), 32 random bytes in .state/openbao/keys/unseal.key, mode 600.
# Initialising: declarative self-initialisation on first start; the root token is used once and revoked, and no
# recovery keys are printed. What it sets up:
#   kv-v2 at substrate/      every secret in deploy/secrets.txt, at substrate/<NAME>, field "value"
#   userpass user substrate   the scripts' login, password in .state/openbao/keys/scripts.pw (mode 600),
#                             allowed only what the "substrate" policy allows: that mount
#   audit (declared below)    a file of every request (no secret values; OpenBao hashes them)
# On one machine the root of trust is still a file you own; what OpenBao adds is one API with policies, an audit
# trail, versions of every secret, and a place to grow (per-service logins, dynamic Postgres credentials).
ui           = false
api_addr     = "http://127.0.0.1:8200"
cluster_addr = "http://127.0.0.1:8201"

# Integrated storage (Raft), one node; OpenBao 2.7 has no "file" storage.
storage "raft" {
  path    = "/openbao/data"
  node_id = "substrate-1"
}

listener "tcp" {
  address     = "127.0.0.1:8200"
  tls_disable = true   # loopback only; nothing else can reach it
}

seal "static" {
  current_key_id = "substrate-1"
  current_key    = "file:///openbao/keys/unseal.key"
}

initialize "mounts" {
  request "kv" {
    operation = "update"
    path      = "sys/mounts/substrate"
    data = {
      type    = "kv"
      options = { version = "2" }
    }
  }
  request "userpass" {
    operation = "update"
    path      = "sys/auth/userpass"
    data      = { type = "userpass" }
  }
}

initialize "access" {
  request "policy" {
    operation = "update"
    path      = "sys/policies/acl/substrate"
    data = {
      policy = <<-EOT
        path "substrate/data/*"     { capabilities = ["create", "read", "update", "delete"] }
        path "substrate/metadata/*" { capabilities = ["read", "list", "delete"] }
      EOT
    }
  }
  request "scripts-login" {
    operation = "update"
    path      = "auth/userpass/users/substrate"
    data = {
      password = {
        eval_type   = "string"
        eval_source = "file"
        path        = "/openbao/keys/scripts.pw"
      }
      token_policies = ["substrate"]
      token_ttl      = "1h"
    }
  }
}

# Every request, to a file beside the data (secret values are HMAC-hashed, not written). Declared here, not
# through the API: OpenBao 2.x only creates audit devices from its configuration.
audit "file" "file" {
  description = "Every request to substrate's secrets"
  options = {
    file_path = "/openbao/data/audit.log"
  }
}
