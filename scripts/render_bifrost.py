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
    """.env, with secrets through the secrets slot (S-31): which providers exist depends on whether keys are set."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from settings import read
    return read()


def ollama_default(env: dict[str, str]) -> str:
    """Where the gateway reaches a model server on this machine: loopback under Nomad (host networking),
    the host's alias from inside a container under compose."""
    if env.get("RUNTIME", "compose") == "nomad":
        return "http://127.0.0.1:11434"
    if env.get("CONTAINER_ENGINE", "podman") == "podman":
        return "http://host.containers.internal:11434"
    return "http://host.docker.internal:11434"


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
                                         "ollama_key_config": {"url": env.get("OLLAMA_URL") or ollama_default(env)}}]}
    return {
        # Bifrost v2.3.2 locks /api and /metrics until an admin account exists, so one is seeded here (dashboard
        # login: admin, BIFROST_ADMIN_PASSWORD). /metrics stays open for Prometheus: it carries counts and cost, no
        # content, and the port is bound to 127.0.0.1. Keys: config.schema.json at transports/v2.3.2.
        "client": {"enforce_auth_on_inference": True, "whitelisted_routes": ["/metrics"]},
        "providers": providers,
        # telemetry: the /metrics Prometheus scrapes (on by default; listed so it stays on beside otel).
        # otel: a span per model call to the collector (S-28), metadata only (tokens, cost, latency, status),
        # never message content. Its service name is the catalog's (model-gateway).
        "plugins": [
            {"name": "telemetry", "enabled": True, "config": {}},
            {"name": "otel", "enabled": True, "config": {
                "service_name": "model-gateway", "collector_url": "env.OTEL_COLLECTOR_URL",
                "trace_type": "genai_extension", "protocol": "http", "disable_content_logging": True}},
        ],
        "governance": {"auth_config": {"is_enabled": True, "admin_username": "admin",
                                       "admin_password": "env.BIFROST_ADMIN_PASSWORD"},
                       "virtual_keys": [{
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
