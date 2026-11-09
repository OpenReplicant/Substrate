#!/usr/bin/env python3
"""This project's Claude Code wiring (S-57): Workbench's MCP server in, kernel's harness entries out.

    python3 scripts/harness.py apply     # back up, then edit .mcp.json and .claude/settings.local.json
    python3 scripts/harness.py status    # what is wired now

`apply` copies both files to .state/harness-backup/<time>/ first. It removes kernel's MCP server ("kernel") and
every hook whose command runs kernel's commands (kernel-mcp, kernel-mcp-hook, kernel-mcp-cue), which `kk up`
wrote, and adds Workbench's MCP server over HTTP, whose headersHelper mints a fresh token for the claude-code
agent at each connection. Claude Code asks to approve a project's MCP server the first time. Standard library only.
"""
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MCP = ROOT / ".mcp.json"
LOCAL = ROOT / ".claude/settings.local.json"
KERNEL_CMDS = ("kernel-mcp", "kernel-mcp-hook", "kernel-mcp-cue")


def load(p: Path) -> dict:
    return json.loads(p.read_text()) if p.exists() else {}


def save(p: Path, d: dict):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, indent=2) + "\n")


def apply() -> dict:
    backup = ROOT / ".state/harness-backup" / time.strftime("%Y%m%dT%H%M%S")
    backup.mkdir(parents=True, exist_ok=True)
    for p in (MCP, LOCAL):
        if p.exists():
            shutil.copy(p, backup / p.name)
    mcp = load(MCP)
    servers = mcp.setdefault("mcpServers", {})
    removed = [n for n in list(servers) if n == "kernel" or any(c in str(servers[n].get("command", "")) for c in KERNEL_CMDS)]
    for n in removed:
        del servers[n]
    servers["workbench"] = {"type": "http", "url": "http://127.0.0.1:8080/wb/api/mcp",
                            "headersHelper": str(ROOT / "scripts/workbench-mcp-headers.sh")}
    save(MCP, mcp)
    local = load(LOCAL)
    hooks_removed = 0
    for event, groups in list((local.get("hooks") or {}).items()):
        kept = []
        for g in groups:
            hs = [h for h in g.get("hooks") or [] if not any(c in str(h.get("command", "")) for c in KERNEL_CMDS)]
            hooks_removed += len(g.get("hooks") or []) - len(hs)
            if hs:
                kept.append({**g, "hooks": hs})
        if kept:
            local["hooks"][event] = kept
        else:
            del local["hooks"][event]
    if "hooks" in local and not local["hooks"]:
        del local["hooks"]
    if local.get("disabledMcpjsonServers"):
        local["disabledMcpjsonServers"] = [s for s in local["disabledMcpjsonServers"] if s not in removed]
        if not local["disabledMcpjsonServers"]:
            del local["disabledMcpjsonServers"]
    save(LOCAL, local)
    return {"backup": str(backup.relative_to(ROOT)), "mcp_removed": removed, "hooks_removed": hooks_removed, "mcp_added": "workbench"}


def status() -> dict:
    mcp, local = load(MCP), load(LOCAL)
    hooks = [h.get("command", "") for gs in (local.get("hooks") or {}).values() for g in gs for h in g.get("hooks") or []]
    return {"mcp_servers": sorted((mcp.get("mcpServers") or {})), "kernel_hooks": sum(any(c in h for c in KERNEL_CMDS) for h in hooks)}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    print(json.dumps(apply() if cmd == "apply" else status(), indent=2))
