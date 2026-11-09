#!/usr/bin/env python3
"""This project's Claude Code wiring (S-57): Workbench's MCP server in .mcp.json.

    python3 scripts/harness.py apply     # back up, then add (or refresh) the entry in .mcp.json
    python3 scripts/harness.py status    # what is wired now

`apply` copies .mcp.json to .state/harness-backup/<time>/ first, then adds Workbench's MCP server over HTTP, whose
headersHelper mints a fresh token for the claude-code agent at each connection. Other servers in the file are left as
they are. Claude Code asks to approve a project's MCP server the first time. Standard library only.
"""
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MCP = ROOT / ".mcp.json"
ENTRY = {"type": "http", "url": "http://127.0.0.1:8080/wb/api/mcp", "headersHelper": str(ROOT / "scripts/workbench-mcp-headers.sh")}


def load(p: Path) -> dict:
    return json.loads(p.read_text()) if p.exists() else {}


def apply() -> dict:
    backup = ROOT / ".state/harness-backup" / time.strftime("%Y%m%dT%H%M%S")
    if MCP.exists():
        backup.mkdir(parents=True, exist_ok=True)
        shutil.copy(MCP, backup / MCP.name)
    mcp = load(MCP)
    mcp.setdefault("mcpServers", {})["workbench"] = ENTRY
    MCP.write_text(json.dumps(mcp, indent=2) + "\n")
    return {"backup": str(backup.relative_to(ROOT)) if backup.exists() else None, "mcp_added": "workbench"}


def status() -> dict:
    servers = load(MCP).get("mcpServers") or {}
    return {"mcp_servers": sorted(servers), "workbench_current": servers.get("workbench") == ENTRY}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    print(json.dumps(apply() if cmd == "apply" else status(), indent=2))
