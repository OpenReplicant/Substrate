"""The gateway's rendered config (scripts/gateway.py render, S-77, S-83), from settings given here: no stack needed.
It should:
- name every caller in CALLERS, each with its own key, and no other
- hold a local-only caller (the store's embeddings) to Ollama even when OpenRouter is configured
- refuse calls without a key, keep no message content, and carry no secret (only env.NAME references or derived keys)
- give no caller a key when GATEWAY_KEY_SECRET is unset

    python3 scripts/tests/test_gateway.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import gateway  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print(("ok  " if ok else "FAIL"), name, "" if ok else detail)


def main():
    env = {"OPENROUTER_API_KEY": "or-secret-value", "OLLAMA_URL": "http://ollama:11434", "GATEWAY_KEY_SECRET": "s" * 32,
           "GATEWAY_DB_PASSWORD": "db-secret-value"}
    cfg = gateway.render(env)
    keys = {k["name"]: k for k in cfg["governance"]["virtual_keys"]}
    check("every caller has a key, and only they do", sorted(keys) == gateway.callers(), sorted(keys))
    check("keys are distinct", len({k["value"] for k in keys.values()}) == len(keys))
    embed = keys["store:embed"]
    check("the store's embeddings reach Ollama only", [p["provider"] for p in embed["provider_configs"]] == ["ollama"],
          embed["provider_configs"])
    check("its key is read from .env", embed["value"] == "env.STORE_EMBED_KEY", embed["value"])
    check("both providers are configured", sorted(cfg["providers"]) == ["ollama", "openrouter"], sorted(cfg["providers"]))
    client = cfg["client"]
    check("a call needs a key", client["enforce_auth_on_inference"] is True)
    check("no message content is logged", client["disable_content_logging"] is True)
    text = json.dumps(cfg)
    check("no secret value is in the file", not any(v in text for v in ("or-secret-value", "db-secret-value", "s" * 32)))
    bare = gateway.render({k: v for k, v in env.items() if k != "GATEWAY_KEY_SECRET"})
    check("no keys without GATEWAY_KEY_SECRET", bare["governance"]["virtual_keys"] == [])
    print(f"{sum(checks)}/{len(checks)} checks passed")
    sys.exit(0 if all(checks) else 1)


if __name__ == "__main__":
    main()
