"""The Claude Code driver, on its own so that a copy of the harness for Kaggle leaves it out: the subscription login stays
on this machine. See drivers.py for the interface."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time

from drivers import HERE, RateLimited, tokens


class ClaudeCode:
    """A stripped-down Claude Code session in print mode, on the logged-in subscription (no API key is read or set).

    Flags (claude 2.1.332, `claude --help`):
      -p --model <alias> --effort low              print mode, the arm's model
      --system-prompt <manager.md>                 replaces Claude Code's own prompt
      --tools ""                                   no built-in tool at all
      --strict-mcp-config --mcp-config <file>      only the stub server; no user or connector server loads
      --allowedTools 'mcp__pm__*'                  so print mode may call them without a prompt
      --setting-sources local                      not the user's settings, hooks or plugins (the scratch directory has none)
      --disable-slash-commands                     no skills or commands
      --no-session-persistence                     nothing saved
      --output-format stream-json --verbose        the trace and the usage
    It runs in an empty scratch directory (no project CLAUDE.md), with CLAUDE* variables of an enclosing Claude
    Code session removed from its environment. Nothing in the user's Claude Code configuration is written.
    """

    def __init__(self, model="haiku", effort="low", prompt_file=None, timeout=300):
        self.name = f"claude-code:{model}"
        self.model, self.effort, self.timeout = model, effort, timeout
        with open(prompt_file or os.path.join(HERE, "manager.md")) as f:
            self.prompt = f.read()
        self.scratch = tempfile.mkdtemp(prefix="pm1a-cwd-")

    def argv(self, mcp_cfg):
        return ["claude", "-p", "--model", self.model, "--effort", self.effort, "--system-prompt", self.prompt,
                "--tools", "", "--strict-mcp-config", "--mcp-config", mcp_cfg, "--allowedTools", "mcp__pm__*",
                "--setting-sources", "local", "--disable-slash-commands", "--no-session-persistence",
                "--output-format", "stream-json", "--verbose"]

    def run(self, text, portfolio, trace_path):
        d = os.path.dirname(os.path.abspath(trace_path))
        pf, cfg = os.path.join(d, "portfolio.json"), os.path.join(d, "mcp.json")
        with open(pf, "w") as f:
            json.dump(portfolio, f)
        with open(cfg, "w") as f:
            json.dump({"mcpServers": {"pm": {"command": "python3", "args": [
                "-I", os.path.join(HERE, "stub_pm.py"), "--portfolio", pf, "--trace", trace_path]}}}, f)
        env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE") and k != "ANTHROPIC_API_KEY"}
        if os.environ.get("PM_PASS_TELEMETRY") and os.environ.get("CLAUDE_CODE_ENABLE_TELEMETRY"):
            env["CLAUDE_CODE_ENABLE_TELEMETRY"] = os.environ["CLAUDE_CODE_ENABLE_TELEMETRY"]  # the cell's observer (S-224)
        t0 = time.time()
        try:
            p = subprocess.run(self.argv(cfg) + [text], cwd=self.scratch, env=env, capture_output=True, text=True,
                               timeout=self.timeout, stdin=subprocess.DEVNULL)
            out, err, rc = p.stdout, p.stderr, p.returncode
        except subprocess.TimeoutExpired as e:
            o = e.stdout
            out, err, rc = (o.decode() if isinstance(o, bytes) else (o or "")), "timeout", -9
        return {**self.parse(out, err, rc), "launch_ts": t0, "wall_s": time.time() - t0, "model": self.model}

    @staticmethod
    def parse(out, err, rc):
        offered, attempts, final, tok, error, limited, model = [], [], "", tokens(), None, False, None
        for line in out.splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            t = e.get("type")
            if t == "system" and e.get("subtype") == "init":
                offered, model = e.get("tools", []), e.get("model")
            elif t == "assistant":
                if e.get("error") == "rate_limit" or e.get("message", {}).get("error") == "rate_limit":
                    limited = True
                for c in e.get("message", {}).get("content", []):
                    if c.get("type") == "tool_use":
                        n = c["name"]
                        attempts.append(n[len("mcp__pm__"):] if n.startswith("mcp__pm__") else n)
            elif t == "rate_limit_event" and (e.get("rate_limit_info") or {}).get("status") == "rejected":
                limited = True
            elif t == "result":
                u = e.get("usage") or {}
                tok = tokens(u.get("input_tokens", 0), u.get("output_tokens", 0), u.get("cache_read_input_tokens", 0),
                             u.get("cache_creation_input_tokens", 0), e.get("total_cost_usd") or 0.0, e.get("num_turns", 0))
                final = e.get("result") or ""
                if e.get("is_error"):
                    error = final or e.get("subtype") or "error"
        blob = f"{error or ''} {err}".lower()
        if limited or ("hit your" in blob and "limit" in blob) or "rate limit" in blob or "rate_limit" in blob:
            raise RateLimited((error or err or "rate limited")[:300])
        if rc not in (0, None) and not error:
            error = (err or f"exit {rc}")[:300]
        return {"final_text": final, "tokens": tok, "offered_tools": offered, "attempts": attempts, "error": error,
                "reported_model": model}
