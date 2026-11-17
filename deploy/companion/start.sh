#!/bin/sh
# The companion's container (S-136): the Claude Code session in tmux session "companion", fed by the channel; the
# background-task runner and the model watcher in the foreground (python3 -m environment.companion run).
#
#   scripts/companion.sh attach      # see the session (detach: ctrl-b d); log in there once with /login
set -eu
S=$HOME/session
mkdir -p "$S" "$HOME/tasks" "$HOME/.claude"
python3 - "$S" <<'PY'
import json, os, sys
from pathlib import Path
from environment.companion import PATTERNS, SESSION_QUEUE
s = Path(sys.argv[1]); home = Path.home()
# the one MCP server the session loads: the channel, on the companion's own database login
(s / "mcp.json").write_text(json.dumps({"mcpServers": {"substrate": {
    "command": "python3", "args": ["-m", "environment.channel", SESSION_QUEUE, *PATTERNS],
    "env": {"PYTHONPATH": "/app", "STORE_URL": os.environ["STORE_URL"]}}}}, indent=2))
# its tools are allowed without asking; nothing else is
(home / ".claude/settings.json").write_text(json.dumps({"permissions": {"allow": [
    "mcp__substrate__ack", "mcp__substrate__act", "mcp__substrate__escalate"]}}, indent=2))
# first-run screens a container need not show again: onboarding, and trust in its own work folder
p = home / ".claude.json"
cfg = json.loads(p.read_text()) if p.exists() else {}
cfg["hasCompletedOnboarding"] = True
cfg.setdefault("projects", {}).setdefault(str(s), {})["hasTrustDialogAccepted"] = True
p.write_text(json.dumps(cfg, indent=2))
PY
model=$(python3 -c 'from environment.companion import connect; v = connect().c.execute("select env.get(%s, %s)", ("companion", "model")).fetchone()[0]; print((v or {}).get("model") or "")' 2>/dev/null || true)
export ANTHROPIC_MODEL="${model:-${COMPANION_MODEL:-claude-haiku-5-5}}"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="${COMPANION_MODEL:-claude-haiku-5-5}"
tmux kill-server 2>/dev/null || true
# the session: no built-in tools (S-134's lean profile), only the channel's; it hands real work to background tasks
tmux new-session -d -s companion -x 200 -y 50 -c "$S" \
  "while true; do claude --model \"$ANTHROPIC_MODEL\" --tools '' --strict-mcp-config --mcp-config $S/mcp.json \
     --append-system-prompt-file /app/deploy/companion/companion.md \
     --dangerously-load-development-channels server:substrate; echo 'the session ended; starting again in 10 s'; sleep 10; done"
exec python3 -m environment.companion run
