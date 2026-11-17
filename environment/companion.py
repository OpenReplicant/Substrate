"""The companion (plan step 4, S-136): its environment's streams and actuators, and the processes that feed and apply
them. The Claude Code session itself is in its own container (deploy/companion), fed by the channel.

    python3 -m environment.companion setup    # its actuators, gates and queues (scripts/up.sh, as the owner)
    python3 -m environment.companion sense    # the clock, the meter and the appliers (service `environment`)
    python3 -m environment.companion run      # in the companion's container: background tasks, the model watcher

Streams (signals, under companion.*):
    owner.message      what the owner says on the UI's page ({"text"})
    clock.tick         the time, every COMPANION_CLOCK_MINUTES (60)
    meter.spend        the gateway's count of the companion's calls (per caller: calls, tokens, cost) since the last
                       tick and today, with the budget; meter.over_budget when today's tokens pass it
    task.done          a background task's result ({"action", "ok", "text"})
    review.proposed / review.decided   from the gates (env.act, env.decide)

Actuators (env.actuator, each applied by one process):
    reply   free     a message to the owner ({"text"}); applied by `sense`, which records it as delivered: the
                     page shows applied replies
    task    free     a background task ({"prompt"}): one `claude -p` run in the companion's container, its result
                     published as task.done. Set to deny while today's tokens are over the budget, free again under it
    budget  propose  a change to the daily token budget ({"daily_tokens", "why"}); applied by `sense` once the owner
                     approves, as the setting companion.budget
    model   propose  a change of the session's model ({"model", "why"}); applied by `sense` as companion.model, which
                     the session takes up (the watcher sends /model); the gateway's key still limits which models
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
import time

import psycopg

from environment import Env
from store.mcp import database_url

ENV = "companion"
SESSION_QUEUE = "companion_session"
PATTERNS = ["companion.owner.#", "companion.clock.#", "companion.meter.#", "companion.task.#", "companion.review.#"]
ACTUATORS = {
    "reply": ("free", "A message to the owner, shown on the UI's page. Input: {\"text\": \"...\"}."),
    "task": ("free", "Start a background task: one Claude Code run in the companion's container with its own tools; "
             "its result arrives as a companion.task.done signal. Input: {\"prompt\": \"what to do, completely\"}."),
    "budget": ("propose", "Propose a new daily token budget for the companion's calls; the owner decides. "
               "Input: {\"daily_tokens\": N, \"why\": \"...\"}."),
    "model": ("propose", "Propose a different model for this session; the owner decides. "
              "Input: {\"model\": \"claude-...\", \"why\": \"...\"}."),
}
LOGIN = "companion"          # the container's database login (scripts/db.py init makes it, a member of env_agent)
SOURCE = "substrate:companion"
DEFAULT_BUDGET = int(os.environ.get("COMPANION_DAILY_TOKENS") or 2_000_000)


def connect() -> Env:
    return Env(psycopg.connect(database_url(), autocommit=True))


def log(*a) -> None:
    print("companion:", *a, file=sys.stderr, flush=True)


# ---- setup (the owner's login)

def setup(e: Env, login: str = LOGIN) -> None:
    for name, (gate, text) in ACTUATORS.items():
        have = e.c.execute("select gate from env.actuator where name = %s", (f"{ENV}.{name}",)).fetchone()
        # a gate someone changed since (the budget's deny on task, or the owner's) is kept
        if have is None:
            e.actuator(f"{ENV}.{name}", gate, SOURCE, text)
    e.subscribe(SESSION_QUEUE, PATTERNS)
    for q in (SESSION_QUEUE, f"act_{ENV}_task"):
        e.c.execute("select env.allow(%s, %s)", (q, login))
    if e.c.execute("select env.get(%s, 'budget')", (ENV,)).fetchone()[0] is None:
        e.c.execute("select env.set(%s, 'budget', %s, %s)", (ENV, json.dumps({"daily_tokens": DEFAULT_BUDGET}), SOURCE))
    print(f"  companion: actuators {', '.join(ACTUATORS)}; session queue {SESSION_QUEUE}; login {login} may read it and the task queue")


# ---- sense: the clock, the meter, the appliers (the owner's login, the gateway's meter login)

def meter_url() -> str | None:
    pw = os.environ.get("GATEWAY_METER_PASSWORD")
    if not pw:
        return None
    return os.environ.get("METER_URL") or f"postgresql://gateway_meter:{pw}@{os.environ.get('PGHOST', 'db')}:5432/gateway"


def spend(since: dt.datetime) -> dict:
    """The gateway's own count of the companion's calls since a time, per caller (S-77: counted by the gateway)."""
    url = meter_url()
    if not url:
        return {}
    with psycopg.connect(url, connect_timeout=5) as c:
        rows = c.execute("""select virtual_key_name, count(*), count(*) filter (where status <> 'success'),
                                   coalesce(sum(prompt_tokens), 0), coalesce(sum(completion_tokens), 0),
                                   coalesce(sum(cached_read_tokens), 0), coalesce(sum(cost), 0)
                              from logs where virtual_key_name like 'companion:%%' and timestamp >= %s
                             group by 1 order by 1""", (since,)).fetchall()
    return {r[0]: {"calls": r[1], "failed": r[2], "prompt_tokens": int(r[3]), "completion_tokens": int(r[4]),
                   "cached_tokens": int(r[5]), "cost_usd": round(float(r[6]), 6)} for r in rows}


def tokens(by_caller: dict) -> int:
    return sum(v["prompt_tokens"] + v["completion_tokens"] for v in by_caller.values())


def budget(e: Env) -> int:
    v = e.c.execute("select env.get(%s, 'budget')", (ENV,)).fetchone()[0] or {}
    return int(v.get("daily_tokens") or DEFAULT_BUDGET)


def tick(e: Env, last: dt.datetime, now: dt.datetime) -> None:
    e.publish(f"{ENV}.clock.tick", {"now": now.astimezone().isoformat(timespec="seconds")}, "clock")
    try:
        today = spend(now.astimezone().replace(hour=0, minute=0, second=0, microsecond=0))
        recent = spend(last)
    except psycopg.Error as x:
        log(f"meter: {x}")
        return
    limit, used = budget(e), tokens(today)
    e.publish(f"{ENV}.meter.spend", {"since": last.isoformat(timespec="seconds"), "recent": recent, "today": today,
                                     "today_tokens": used, "daily_budget_tokens": limit}, "gateway meter")
    gate = e.c.execute("select gate, set_by from env.actuator where name = %s", (f"{ENV}.task",)).fetchone()
    if used > limit and gate[0] == "free":
        e.actuator(f"{ENV}.task", "deny", "budget")
        e.publish(f"{ENV}.meter.over_budget", {"today_tokens": used, "daily_budget_tokens": limit,
                                               "effect": "background tasks are refused until today's tokens are under the budget"}, "gateway meter")
    elif used <= limit and gate == ("deny", "budget"):
        e.actuator(f"{ENV}.task", "free", "budget")


MODEL = re.compile(r"^claude-[a-z0-9.-]{1,60}$")


def apply(e: Env, name: str, m: dict) -> None:
    action, inp = m["action"], m.get("input") or {}
    if name == "reply":
        ok = isinstance(inp.get("text"), str) and inp["text"].strip() != ""
        e.done(action, {"shown": ok} if ok else {"error": "a reply needs text"}, ok)
    elif name == "budget":
        n = inp.get("daily_tokens")
        if isinstance(n, int) and 0 < n <= 10**9:
            e.c.execute("select env.set(%s, 'budget', %s, %s, %s)", (ENV, json.dumps({"daily_tokens": n}), m.get("by") or "?", action))
            e.done(action, {"daily_tokens": n})
        else:
            e.done(action, {"error": "daily_tokens must be a positive whole number"}, False)
    elif name == "model":
        model = inp.get("model")
        if isinstance(model, str) and MODEL.match(model):
            e.c.execute("select env.set(%s, 'model', %s, %s, %s)", (ENV, json.dumps({"model": model}), m.get("by") or "?", action))
            e.done(action, {"model": model, "note": "the session switches at its next turn; the gateway's key decides which models it may reach"})
        else:
            e.done(action, {"error": "not a Claude model name"}, False)


def sense() -> None:
    minutes = float(os.environ.get("COMPANION_CLOCK_MINUTES") or 60)
    e, last = None, dt.datetime.now(dt.timezone.utc)
    next_tick = time.monotonic() + 5              # one tick soon after start, so the session knows the time
    while True:
        try:
            e = e if e and not e.c.closed else connect()
            for name in ("reply", "budget", "model"):
                for m in e.read(f"act_{ENV}_{name}", 60, 10):
                    apply(e, name, m)
            if time.monotonic() >= next_tick:
                now = dt.datetime.now(dt.timezone.utc)
                tick(e, last, now)
                last, next_tick = now, time.monotonic() + minutes * 60
        except psycopg.OperationalError as x:
            log(f"database: {x}; retrying")
            e = None
            time.sleep(5)
        except psycopg.Error as x:
            log(f"{type(x).__name__}: {x}")
        time.sleep(1)


# ---- run: inside the companion's container (its own login)

TASK_TIMEOUT = int(os.environ.get("COMPANION_TASK_SECONDS") or 1800)


def task(prompt: str) -> tuple[bool, str]:
    """One background task: a headless Claude Code run with its tools, in the container's work folder, under the
    task caller's key. The database's settings are not passed on."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PG", "STORE_URL", "COMPANION_SESSION"))}
    if os.environ.get("COMPANION_TASK_KEY"):
        env["ANTHROPIC_CUSTOM_HEADERS"] = f"x-bf-vk: {os.environ['COMPANION_TASK_KEY']}"
    cmd = ["claude", "-p", prompt, "--output-format", "json", "--permission-mode", "bypassPermissions",
           "--strict-mcp-config", "--mcp-config", '{"mcpServers": {}}']
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=TASK_TIMEOUT, env=env,
                           cwd=os.environ.get("COMPANION_TASKS_DIR") or os.path.expanduser("~/tasks"))
    except subprocess.TimeoutExpired:
        return False, f"stopped after {TASK_TIMEOUT} s"
    try:
        out = json.loads(p.stdout)
        return (p.returncode == 0 and not out.get("is_error")), str(out.get("result") or "")[:20000]
    except json.JSONDecodeError:
        return False, (p.stdout + p.stderr)[-4000:]


def set_model(model: str) -> None:
    subprocess.run(["tmux", "send-keys", "-t", "companion", f"/model {model}", "Enter"], check=False)


def run() -> None:
    os.makedirs(os.environ.get("COMPANION_TASKS_DIR") or os.path.expanduser("~/tasks"), exist_ok=True)
    e, model = None, os.environ.get("ANTHROPIC_MODEL")
    while True:
        try:
            e = e if e and not e.c.closed else connect()
            want = (e.c.execute("select env.get(%s, 'model')", (ENV,)).fetchone()[0] or {}).get("model")
            if want and want != model:
                set_model(want)
                model = want
            for m in e.read(f"act_{ENV}_task", TASK_TIMEOUT + 60, 1):
                prompt = (m.get("input") or {}).get("prompt")
                if not isinstance(prompt, str) or not prompt.strip():
                    e.done(m["action"], {"error": "a task needs a prompt"}, False)
                    continue
                log(f"task {m['action']}: started")
                ok, text = task(prompt)
                e.done(m["action"], {"ok": ok, "chars": len(text)}, ok)
                e.publish(f"{ENV}.task.done", {"action": m["action"], "ok": ok, "text": text}, "companion task runner")
                log(f"task {m['action']}: {'done' if ok else 'failed'}")
        except psycopg.OperationalError as x:
            log(f"database: {x}; retrying")
            e = None
            time.sleep(5)
        except psycopg.Error as x:
            log(f"{type(x).__name__}: {x}")
        time.sleep(2)


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "setup":
        setup(connect())
    elif cmd == "sense":
        sense()
    elif cmd == "run":
        run()
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
