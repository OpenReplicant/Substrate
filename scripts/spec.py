#!/usr/bin/env python3
"""Where the spec's build plan stands (docs/build.yaml), for people, scripts/check.sh and Claude Code's hook.

    python3 scripts/spec.py status            # every step
    python3 scripts/spec.py next [--short]    # the step to work on now
    python3 scripts/spec.py set ID STATUS [--waiting-on TEXT]   # todo, doing, done, blocked, dropped
    python3 scripts/spec.py hook              # SessionStart hook output (.claude/settings.json)

Standard library only (it runs on the host, where only python3 is promised, S-19). docs/build.yaml is read with
a small parser for its own simple layout; `set` edits one line, so comments and order stay as they are.
"""
from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "docs" / "build.yaml"
SPEC = ROOT / "docs" / "spec.md"
STATUSES = ("todo", "doing", "done", "blocked", "dropped")


def steps() -> list[dict]:
    out, cur, key = [], None, None
    for line in PLAN.read_text().splitlines():
        if line.startswith("  - id:"):
            cur = {"id": int(line.split(":", 1)[1]), "after": [], "needs_owner": False}
            out.append(cur)
            key = None
            continue
        if cur is None:
            continue
        m = re.match(r"^    ([a-z_]+):\s?(.*)$", line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            if key == "after":
                cur["after"] = [int(x) for x in re.findall(r"\d+", val)]
            elif key == "needs_owner":
                cur["needs_owner"] = val == "true"
            else:
                cur[key] = val.strip('"') if val not in (">-", "|") else ""
        elif key and line.startswith("      "):   # a folded value's continuation
            cur[key] = (cur.get(key, "") + " " + line.strip()).strip()
    return out


def nxt(plan: list[dict]) -> dict | None:
    done = {s["id"] for s in plan if s.get("status") in ("done", "dropped")}
    for s in plan:   # a step already started comes first
        if s.get("status") == "doing":
            return s
    for s in plan:
        if s.get("status") == "todo" and all(a in done for a in s["after"]):
            return s
    return None


def line(s: dict) -> str:
    owner = " (needs the owner)" if s["needs_owner"] else ""
    return f"step {s['id']}: {s['title']} [{s.get('status')}]{owner}"


def set_status(sid: int, status: str, waiting: str | None) -> int:
    if status not in STATUSES:
        print(f"status must be one of {', '.join(STATUSES)}", file=sys.stderr)
        return 2
    lines = PLAN.read_text().splitlines()
    i = next((n for n, ln in enumerate(lines) if ln == f"  - id: {sid}"), None)
    if i is None:
        print(f"no step {sid} in docs/build.yaml", file=sys.stderr)
        return 1
    end = next((n for n in range(i + 1, len(lines)) if lines[n].startswith("  - id:")), len(lines))
    block = lines[i:end]
    block = [ln for ln in block if not re.match(r"^    (status|waiting_on|done_on):", ln)]
    extra = [f"    status: {status}"]
    if status == "done":
        extra.append(f"    done_on: {datetime.date.today().isoformat()}")
    if waiting:
        extra.append(f"    waiting_on: {json.dumps(waiting)}")
    # keep the step's trailing blank line, if it had one, after the new lines
    trail = []
    while block and not block[-1].strip():
        trail.append(block.pop())
    lines[i:end] = block[:1] + extra + block[1:] + trail
    PLAN.write_text("\n".join(lines) + "\n")
    print(f"step {sid}: {status}")
    return 0


def hook() -> int:
    """SessionStart: say where the build-out stands, briefly (well under the 2,000-character preview)."""
    if not SPEC.exists() or not PLAN.exists():
        return 0
    plan = steps()
    s = nxt(plan)
    done = sum(1 for x in plan if x.get("status") == "done")
    if not (ROOT / ".env").exists():
        text = ("Substrate's spec is in place (docs/spec.md) and this machine is not set up yet. Unless the owner "
                "asks for something else, start with the setup skill (step 0 of docs/build.yaml), then continue "
                "with the build-out skill.")
    elif s is None:
        text = (f"Substrate's spec (docs/spec.md): {done} of {len(plan)} steps done; nothing is ready to work on "
                "(the rest are blocked, dropped or wait on earlier steps). Say so if the owner asks.")
    else:
        text = (f"Substrate's spec is in place (docs/spec.md): {done} of {len(plan)} build steps done. Next: "
                f"{line(s)}. Unless the owner asks for something else, continue it with the build-out skill; "
                "decisions that are the owner's wait for them.")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
    return 0


def main(argv: list[str]) -> int:
    if not PLAN.exists():
        print("no docs/build.yaml: no spec is being built out")
        return 0 if argv[:1] == ["hook"] else 1
    cmd = argv[0] if argv else "status"
    if cmd == "hook":
        return hook()
    plan = steps()
    if cmd == "status":
        for s in plan:
            print(line(s) + (f"  waiting on: {s['waiting_on']}" if s.get("waiting_on") else ""))
        n = nxt(plan)
        print("next: " + (line(n) if n else "none ready"))
        return 0
    if cmd == "next":
        n = nxt(plan)
        if "--short" in argv:
            done = sum(1 for x in plan if x.get("status") == "done")
            print(f"{done}/{len(plan)} done; next " + (line(n) if n else "none ready"))
            return 0
        if not n:
            print("none ready")
            return 0
        print(line(n))
        for k in ("where", "spec", "check", "notes", "waiting_on"):
            if n.get(k):
                print(f"  {k}: {n[k]}")
        return 0
    if cmd == "set" and len(argv) >= 3:
        waiting = argv[argv.index("--waiting-on") + 1] if "--waiting-on" in argv else None
        return set_status(int(argv[1]), argv[2], waiting)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
