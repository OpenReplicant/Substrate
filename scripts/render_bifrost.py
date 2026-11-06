"""Render the gateway's config.json from .env: only the providers this machine has (S-14).

    python3 scripts/render_bifrost.py            # writes .state/bifrost/config.json

Provider keys are never written here: Bifrost reads them from its environment (env.NAME), which compose
fills from .env. Format from Bifrost v2.3.2's docs (quickstart/gateway/provider-configuration.mdx,
providers/supported-providers/{openrouter,ollama}.mdx, features/governance/virtual-keys.mdx).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read_env(path: Path) -> dict[str, str]:
    env = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def render(env: dict[str, str]) -> dict:
    providers: dict[str, dict] = {
        # Always present: with no API key, Claude Code's subscription token is forwarded to Anthropic and the
        # virtual key (x-bf-vk) governs the call (Bifrost's docs/cli-agents/claude-code.mdx).
        "anthropic": {"keys": [{"name": "anthropic-api", "value": "env.ANTHROPIC_API_KEY",
                                "models": ["*"], "weight": 1.0}] if env.get("ANTHROPIC_API_KEY") else []},
    }
    if env.get("OPENROUTER_API_KEY"):
        providers["openrouter"] = {"keys": [{"name": "openrouter", "value": "env.OPENROUTER_API_KEY",
                                             "models": ["*"], "weight": 1.0}]}
    if env.get("OLLAMA_ENABLED", "true").lower() == "true":
        providers["ollama"] = {"keys": [{"name": "ollama-local", "value": "", "models": ["*"], "weight": 1.0,
                                         "ollama_key_config": {"url": env.get("OLLAMA_URL")
                                                               or "http://host.docker.internal:11434"}}]}
    return {
        "client": {"enforce_auth_on_inference": True},
        "providers": providers,
        "governance": {"virtual_keys": [{
            "id": "vk-substrate",
            "name": "substrate",
            "value": "env.BIFROST_VIRTUAL_KEY",
            "description": "Claude Code and kernel modules on this machine",
            "is_active": True,
            "provider_configs": [{"provider": p, "allowed_models": ["*"], "key_ids": ["*"]} for p in providers],
        }]},
    }


def main() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        sys.exit(".env is missing: run scripts/up.sh (it creates .env from .env.example)")
    out = ROOT / ".state/bifrost/config.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(render(read_env(env_file)), indent=2) + "\n")
    print(f"wrote {out.relative_to(ROOT)}: providers {', '.join(render(read_env(env_file))['providers'])}")


if __name__ == "__main__":
    main()
