"""Repair: point a project's Claude Code files at substrate's bin/ wrappers (S-19).

    python3 scripts/point_harness.py PROJECT

scripts/up.sh no longer needs this: it runs `kk up --commands-dir bin/` (kernel D-95), which writes the
wrappers directly. Use it for a project connected by an older kernel, whose files name kernel-mcp,
kernel-mcp-hook and kernel-mcp-cue as the tools container sees them (kk up keeps hooks it already finds). This rewrites those commands, in PROJECT/.mcp.json and
PROJECT/.claude/settings.local.json, to the wrappers in bin/, which run the same commands inside the
container. Everything else in the files is kept. Running it again changes nothing.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "bin"
TOOLS = ("kernel-mcp-hook", "kernel-mcp-cue", "kernel-mcp")   # longest first, for the pattern below
PATTERN = re.compile(r"(?<![\w./-])(?:/[^\s\"']*/)?(" + "|".join(map(re.escape, TOOLS)) + r")(?![\w-])")


def repoint(text: str) -> str:
    return PATTERN.sub(lambda m: str(BIN / m.group(1)), text)


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    project = Path(sys.argv[1]).resolve()
    changed = []
    mcp = project / ".mcp.json"
    if mcp.exists():
        cfg = json.loads(mcp.read_text() or "{}")
        entry = cfg.get("mcpServers", {}).get("kernel")
        if entry and entry.get("command") != str(BIN / "kernel-mcp"):
            entry["command"] = str(BIN / "kernel-mcp")
            mcp.write_text(json.dumps(cfg, indent=2) + "\n")
            changed.append(".mcp.json")
    local = project / ".claude/settings.local.json"
    if local.exists():
        settings = json.loads(local.read_text() or "{}")
        for entries in settings.get("hooks", {}).values():
            for entry in entries:
                for hook in entry.get("hooks", []):
                    cmd = hook.get("command", "")
                    if any(t in cmd for t in TOOLS):
                        hook["command"] = repoint(cmd)
        text = json.dumps(settings, indent=2) + "\n"
        if text != local.read_text():
            local.write_text(text)
            changed.append(".claude/settings.local.json")
    print("  pointed at bin/: " + (", ".join(changed) if changed else "already"))


if __name__ == "__main__":
    main()
