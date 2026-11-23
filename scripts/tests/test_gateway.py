"""The gateway's rendered config (scripts/gateway.py render, S-77, S-83), from settings given here: no stack needed.
It should:
- name every caller in CALLERS, each with its own key, and no other
- hold a local-only caller (the store's embeddings) to Ollama even when OpenRouter is configured
- hold the companion's callers to Anthropic (on the owner's own login: no Anthropic key in the config)
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
    check("the providers are configured", sorted(cfg["providers"]) == ["anthropic", "ollama", "openrouter"], sorted(cfg["providers"]))
    local = gateway.render({**env, "LLM_MODEL": "model.gguf"})
    lk = {k["name"]: k for k in local["governance"]["virtual_keys"]}
    check("with a local model, it is a provider of its own", "local" in local["providers"]
          and local["providers"]["local"]["network_config"]["base_url"] == "http://llm:8080")
    check("the voice head reaches local providers only (what is said aloud stays here)",
          {p["provider"] for p in lk["voice:head"]["provider_configs"]} <= set(gateway.LOCAL)
          and "local" in {p["provider"] for p in lk["voice:head"]["provider_configs"]}, lk["voice:head"]["provider_configs"])
    both = gateway.render({**env, "LLM_MODEL": "model.gguf", "LLM_FAST_MODEL": "fast.gguf"})
    bk = {k["name"]: k for k in both["governance"]["virtual_keys"]}
    check("with a fast model too, it is provider fast, which the voice head and the worker reach (S-169)",
          both["providers"]["fast"]["network_config"]["base_url"] == "http://llm-fast:8080"
          and all("fast" in {p["provider"] for p in bk[c]["provider_configs"]} for c in ("voice:head", "worker:loop")))
    check("the companion does not reach the local model", all(p["provider"] == "anthropic" for c in ("companion:session", "companion:task")
                                                               for p in lk[c]["provider_configs"]))
    check("Anthropic has no key of its own (only a caller's Claude login reaches it)", cfg["providers"]["anthropic"] == {"keys": []})
    for c in ("companion:session", "companion:task"):
        pc = keys[c]["provider_configs"]
        check(f"{c} reaches Anthropic only, Haiku by default", [p["provider"] for p in pc] == ["anthropic"]
              and pc[0]["allowed_models"] == ["regex:claude-haiku.*"], pc)
        check(f"{c}'s key is read from .env", keys[c]["value"].startswith("env.COMPANION_"), keys[c]["value"])
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
