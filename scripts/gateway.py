#!/usr/bin/env python3
"""Route this project's Claude Code through the gateway, or stop (S-14). Edits only the env keys it owns
in .claude/settings.local.json, keeping what kk up wrote. Takes effect in the next Claude Code session.

    scripts/gateway.py on                    # your Claude subscription, governed by the virtual key (default)
    scripts/gateway.py on --mode api-key     # the virtual key as the credential (provider keys in Bifrost)
    scripts/gateway.py off                   # straight to Anthropic again
    scripts/gateway.py status

Modes from Bifrost's docs/cli-agents/claude-code.mdx (v2.3.2). In subscription mode, do not set
ANTHROPIC_AUTH_TOKEN, ANTHROPIC_API_KEY or apiKeyHelper: each replaces the subscription login.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OWNED = ("ANTHROPIC_BASE_URL", "ANTHROPIC_CUSTOM_HEADERS", "ANTHROPIC_AUTH_TOKEN")


def read_env() -> dict[str, str]:
    env = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            k, sep, v = line.partition("=")
            if sep and not k.startswith("#"):
                env[k.strip()] = v.strip()
    return env


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("action", choices=("on", "off", "status"))
    ap.add_argument("--mode", choices=("subscription", "api-key"), default="subscription")
    ap.add_argument("--project", type=Path, default=ROOT, help="the project whose settings to change")
    a = ap.parse_args()
    path = a.project / ".claude/settings.local.json"
    settings = json.loads(path.read_text()) if path.exists() else {}
    env = settings.setdefault("env", {})

    if a.action == "status":
        if not env.get("ANTHROPIC_BASE_URL"):
            print("not routed through the gateway")
            sys.exit(1)
        mode = "api-key" if env.get("ANTHROPIC_AUTH_TOKEN") else "subscription"
        print(f"routed through {env['ANTHROPIC_BASE_URL']} ({mode})")
        return

    for k in OWNED:
        env.pop(k, None)
    if a.action == "on":
        cfg = read_env()
        vk, port = cfg.get("BIFROST_VIRTUAL_KEY"), cfg.get("BIFROST_PORT") or "8090"
        if not vk:
            sys.exit("BIFROST_VIRTUAL_KEY is empty in .env: run scripts/up.sh first")
        env["ANTHROPIC_BASE_URL"] = f"http://127.0.0.1:{port}/anthropic"
        if a.mode == "subscription":
            env["ANTHROPIC_CUSTOM_HEADERS"] = f"x-bf-vk: {vk}"
        else:
            env["ANTHROPIC_AUTH_TOKEN"] = vk
    if not env:
        settings.pop("env")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n")
    print(f"{a.action}: {path} (restart Claude Code for it to apply)")


if __name__ == "__main__":
    main()
