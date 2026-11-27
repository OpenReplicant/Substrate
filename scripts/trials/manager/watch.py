"""The supervisor's first half, as a trial (docs/manager-agent.md, "The supervisor"; S-223): watch Claude Code's
background sessions and print the signals the supervisor would publish, one JSON object a line. Nothing is written
anywhere and no session is started, stopped or resumed.

    python3 scripts/trials/manager/watch.py --once          # one look: every session's state now
    python3 scripts/trials/manager/watch.py [--every 15]    # keep looking; print only transitions

It runs on the host (it calls `claude`), with python3's standard library only (CLAUDE.md rule 6). It reads
`claude agents --json --all` (fields read at code.claude.com/docs/en/agent-view, 2026-11-27, Claude Code 2.1.332:
id, sessionId, name, cwd, kind, state working|blocked|done|failed|stopped, status busy|waiting|idle, waitingFor), and
for a session that ends failed or stopped it reads the tail of `claude logs <id>` for a usage-limit line
("You've hit your session limit · resets 3:45pm", code.claude.com/docs/en/errors), so a stop by the limit is told
apart from a failure and carries its reset time. A session working with no change for --stall seconds is a stall.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time

LIMIT = re.compile(r"You've hit your (session|weekly|Opus|Sonnet|monthly spend|individual usage) limit(?: · resets ([^\n]+))?")
STATE = {"working": "working", "blocked": "needs_input", "done": "finished", "failed": "failed", "stopped": "stopped"}


def claude(*args: str, timeout: int = 30) -> tuple[int, str]:
    try:
        r = subprocess.run(["claude", *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, f"{type(e).__name__}: {e}"
    return r.returncode, r.stdout + r.stderr


def sessions() -> list[dict]:
    code, out = claude("agents", "--json", "--all")
    if code:
        raise RuntimeError(out.strip()[:300])
    return [s for s in json.loads(out) if s.get("kind") == "background"]


def why_stopped(sid: str) -> dict:
    """A failed or stopped session: was it the usage limit? Its log's tail says (needs Claude Code's supervisor up)."""
    code, out = claude("logs", sid)
    if code:
        return {"cause": "unknown", "detail": out.strip()[:200]}
    m = None
    for m in LIMIT.finditer(out):
        pass
    if m:
        return {"cause": "usage_limit", "limit": m.group(1), "resets": (m.group(2) or "").strip() or None}
    return {"cause": "error", "detail": out.strip().splitlines()[-1][:200] if out.strip() else ""}


def signal(s: dict, kind: str, extra: dict | None = None) -> dict:
    """The signal the supervisor would publish: pm.worker.<state>, body with references only, never a transcript."""
    body = {k: s.get(k) for k in ("id", "sessionId", "name", "cwd", "state", "status", "waitingFor") if s.get(k) is not None}
    return {"key": f"pm.worker.{kind}", "body": {**body, **(extra or {})}, "at": int(time.time())}


def look(seen: dict, stall: int, everything: bool) -> list[dict]:
    out, now = [], time.time()
    for s in sessions():
        sid, state = s["id"], s.get("state")
        key = (state, s.get("status"), s.get("waitingFor"))
        before = seen.get(sid)
        if before is None or before["key"] != key or everything:
            kind = STATE.get(state, "unknown")
            extra = why_stopped(sid) if state in ("failed", "stopped") else None
            if extra and extra.get("cause") == "usage_limit":
                kind = "limited"
            out.append(signal(s, kind, extra))
            seen[sid] = {"key": key, "since": now, "stalled": False}
        elif state == "working" and not before["stalled"] and now - before["since"] > stall:
            before["stalled"] = True
            out.append(signal(s, "stalled", {"for_seconds": int(now - before["since"])}))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--once", action="store_true", help="one look, every session's state")
    ap.add_argument("--every", type=int, default=15, help="seconds between looks")
    ap.add_argument("--stall", type=int, default=1800, help="seconds working with no change before a stall")
    a = ap.parse_args()
    seen: dict = {}
    while True:
        try:
            for sig in look(seen, a.stall, a.once):
                print(json.dumps(sig, ensure_ascii=False), flush=True)
        except (RuntimeError, json.JSONDecodeError) as e:
            print(json.dumps({"key": "pm.supervisor.error", "body": {"detail": str(e)[:300]}}), flush=True)
        if a.once:
            return
        time.sleep(a.every)


if __name__ == "__main__":
    sys.exit(main())
