"""The companion's environment (plan step 4), in a throwaway database it drops after (ADMIN_URL from scripts/test.sh).
It should:
- give the companion's login (a member of env_agent) only what it needs: publish, act, read and acknowledge its
  own queues, report its own actions done; never decide a proposal, change a gate, set a setting, read the record
  or another queue; and keep which login really wrote each signal and action, whatever source it claims
- apply replies, and budget and model changes only once the owner has approved them, refusing bad input
- publish the clock and the meter on a tick, and refuse background tasks while today's tokens are over the budget,
  freeing them again under it
- on the UI: take the owner's message and decision only as JSON from its own origin, and show the conversation

    scripts/test.sh scripts/tests/test_companion.py
"""
import json
import os
import sys
import threading
import datetime as dt
import urllib.error
import urllib.request
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from environment import db as envdb  # noqa: E402
from environment import Env  # noqa: E402
from environment import companion as comp  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print(("ok  " if ok else "FAIL"), name, "" if ok else detail)


def refused(fn, needle=""):
    try:
        fn()
    except psycopg.Error as e:
        return needle in str(e)
    return False


def main():
    admin = os.environ["ADMIN_URL"]
    name, login = f"comp_test_{os.getpid()}", f"comp_login_{os.getpid()}"
    with psycopg.connect(admin, autocommit=True) as a:
        a.execute(f"create database {name}")
    url = admin.rsplit("/", 1)[0] + "/" + name
    try:
        with psycopg.connect(url, autocommit=True) as c:
            envdb.migrate(c)
            c.execute(f"create role {login} login password 'test-only'")
            c.execute(f"grant env_agent to {login}")
            owner = Env(c)
            comp.setup(owner, login)
            host = url.split("@", 1)[1].split("/", 1)[0]
            with psycopg.connect(f"postgresql://{login}:test-only@{host}/{name}", autocommit=True) as ac:
                agent(owner, Env(ac), login)
            appliers(owner)
            ui(url, owner)
    finally:
        with psycopg.connect(admin, autocommit=True) as a:
            a.execute(f"drop database {name} with (force)")
            a.execute(f"drop role if exists {login}")
    print(f"{sum(checks)}/{len(checks)} checks passed")
    sys.exit(0 if all(checks) else 1)


def agent(owner: Env, me: Env, login: str):
    sid = me.publish("companion.owner.message", {"text": "pretending to be the owner"}, "owner")
    row = owner.c.execute("select source, login from env.signal where id = %s", (sid,)).fetchone()
    check("the login may publish, and the record keeps who really did", row == ("owner", login), row)
    got = me.read(comp.SESSION_QUEUE, 30, 10)
    check("it reads its own session queue", [m["key"] for m in got] == ["companion.owner.message"], got)
    check("and acknowledges there", me.ack(comp.SESSION_QUEUE, [got[0]["msg_id"]]) == [got[0]["msg_id"]])
    a, status = me.act("companion.budget", {"daily_tokens": 10**8, "why": "more"}, "companion")
    check("it may act: a budget change is proposed", status == "proposed")
    check("it may not decide its own proposal, under any name",
          refused(lambda: me.decide(a, True, "owner"), "permission denied"))
    check("it may not change a gate", refused(lambda: me.actuator("companion.budget", "free", "companion"), "permission denied"))
    check("it may not set a setting directly",
          refused(lambda: me.c.execute("select env.set('companion', 'budget', '{\"daily_tokens\": 1}', 'x')"), "permission denied"))
    check("it may not write the settings table",
          refused(lambda: me.c.execute("insert into env.setting (env, name, value, set_by) values ('companion', 'model', '{}', 'x')"), "permission denied"))
    check("it may not read the record", refused(lambda: me.c.execute("select * from env.signal"), "permission denied"))
    check("it may not read another queue", refused(lambda: me.read("act_companion_reply", 1, 1), "may not read"))
    check("nor pgmq directly", refused(lambda: me.c.execute("select * from pgmq.read('act_companion_reply', 1, 1)"), "permission denied"))
    check("nor bind to someone else's queue", refused(lambda: me.subscribe("act_companion_reply", ["companion.#"]), "is not"))
    r, _ = me.act("companion.reply", {"text": "hi"}, "companion")
    check("it may not report a reply done (the applier does)", refused(lambda: me.done(r, {}), "does not apply"))
    t, _ = me.act("companion.task", {"prompt": "count to three"}, "companion")
    m = me.read("act_companion_task", 30, 1)
    me.done(t, {"ok": True})
    check("it runs its own tasks: reads the task queue and reports done",
          m and m[0]["action"] == t and owner.c.execute("select status from env.action where id = %s", (t,)).fetchone()[0] == "applied")
    check("it may read its settings", me.c.execute("select env.get('companion', 'budget')").fetchone()[0]["daily_tokens"] > 0)
    owner.decide(a, False, "owner", "test")


def drain(e: Env):
    for name in ("reply", "budget", "model"):
        for m in e.read(f"act_companion_{name}", 30, 10):
            comp.apply(e, name, m)


def status(e, a):
    return e.c.execute("select status, result from env.action where id = %s", (a,)).fetchone()


def appliers(e: Env):
    r, _ = e.act("companion.reply", {"text": "hello"}, "companion")
    bad, _ = e.act("companion.reply", {"text": " "}, "companion")
    drain(e)
    check("a reply is applied as shown", status(e, r)[0] == "applied" and status(e, bad)[0] == "failed", (status(e, r), status(e, bad)))
    b, st = e.act("companion.budget", {"daily_tokens": 123456, "why": "test"}, "companion")
    drain(e)
    check("a budget change waits for the owner", st == "proposed" and e.c.execute("select env.get('companion', 'budget')").fetchone()[0]["daily_tokens"] != 123456)
    e.decide(b, True, "owner")
    drain(e)
    check("approved, it becomes the budget", e.c.execute("select env.get('companion', 'budget')").fetchone()[0] == {"daily_tokens": 123456}
          and e.c.execute("select action from env.current where env = 'companion' and name = 'budget'").fetchone()[0] == b)
    m, _ = e.act("companion.model", {"model": "gpt-4; drop table", "why": "x"}, "companion")
    e.decide(m, True, "owner")
    drain(e)
    check("a model that is not a Claude model name is refused even when approved", status(e, m)[0] == "failed", status(e, m))
    m2, _ = e.act("companion.model", {"model": "claude-sonnet-5-5", "why": "harder work"}, "companion")
    e.decide(m2, True, "owner")
    drain(e)
    check("an approved model becomes the setting", e.c.execute("select env.get('companion', 'model')").fetchone()[0] == {"model": "claude-sonnet-5-5"})
    # the tick: clock and meter; over budget, tasks are refused; under it, free again
    e.subscribe("watch", ["companion.clock.#", "companion.meter.#"])
    now = dt.datetime.now(dt.timezone.utc)
    real = comp.spend
    try:
        comp.spend = lambda since: {"companion:session": {"calls": 9, "failed": 0, "prompt_tokens": 200000, "completion_tokens": 1,
                                                          "cached_tokens": 0, "cost_usd": 0.0}}
        comp.tick(e, now, now)
        keys = [m["key"] for m in e.read("watch", 30, 10)]
        gate = e.c.execute("select gate, set_by from env.actuator where name = 'companion.task'").fetchone()
        check("a tick publishes the clock and the meter; over budget it says so",
              keys == ["companion.clock.tick", "companion.meter.spend", "companion.meter.over_budget"], keys)
        check("and background tasks are refused", gate == ("deny", "budget") and e.act("companion.task", {"prompt": "x"}, "c")[1] == "denied", gate)
        comp.spend = lambda since: {}
        comp.tick(e, now, now)
        check("under the budget again, they are free", e.c.execute("select gate from env.actuator where name = 'companion.task'").fetchone()[0] == "free")
        e.actuator("companion.task", "deny", "owner")
        comp.tick(e, now, now)
        check("a deny the owner set is not lifted by the budget", e.c.execute("select gate from env.actuator where name = 'companion.task'").fetchone()[0] == "deny")
        e.actuator("companion.task", "free", "owner")
    finally:
        comp.spend = real


def ui(url: str, e: Env):
    os.environ["OWNER_NAME"] = "owner"
    from ui import server
    srv = server.serve("127.0.0.1", 0, url, url)   # kernel: never read here (its Store connects on first query)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def post(path, body, headers):
        r = urllib.request.Request(base + path, json.dumps(body).encode(), headers, method="POST")
        try:
            with urllib.request.urlopen(r, timeout=10) as x:
                return x.status, json.loads(x.read())
        except urllib.error.HTTPError as x:
            return x.code, json.loads(x.read())
    js = {"Content-Type": "application/json"}
    here = {**js, "Origin": base.replace("127.0.0.1", "127.0.0.1")}
    host_origin = {**js, "Origin": f"http://127.0.0.1:{srv.server_address[1]}"}
    try:
        check("the page refuses a message with no Origin", post("/api/companion/say", {"text": "x"}, js)[0] == 403)
        check("and one from another origin", post("/api/companion/say", {"text": "x"}, {**js, "Origin": "http://evil.example"})[0] == 403)
        check("and a cross-site fetch", post("/api/companion/say", {"text": "x"}, {**host_origin, "Sec-Fetch-Site": "cross-site"})[0] == 403)
        check("and a form post", post("/api/companion/say", {"text": "x"}, {**host_origin, "Content-Type": "text/plain"})[0] == 403)
        code, out = post("/api/companion/say", {"text": "hello from the page"}, here)
        row = e.c.execute("select key, source, body from env.signal where id = %s", (out.get("signal"),)).fetchone()
        check("from the page it is the owner's message", code == 200 and row == ("companion.owner.message", "owner", {"text": "hello from the page"}), (code, out, row))
        a, _ = e.act("companion.budget", {"daily_tokens": 5, "why": "x"}, "companion")
        code, out = post("/api/companion/decide", {"action": a, "approve": False, "reason": "no"}, here)
        check("the owner decides a proposal there", code == 200 and out["status"] == "refused", (code, out))
        code, out = post("/api/companion/decide", {"action": a, "approve": True}, here)
        check("a decided one cannot be decided again", code == 400 and "not waiting" in out["error"], (code, out))
        a2, _ = e.act("companion.budget", {"daily_tokens": 5, "why": "x"}, "owner")
        code, out = post("/api/companion/decide", {"action": a2, "approve": True}, here)
        check("nor can the owner approve a proposal made in the owner's name", code == 400, (code, out))
        with urllib.request.urlopen(base + "/api/companion", timeout=10) as r:
            d = json.loads(r.read())
        kinds = [c["kind"] for c in d["conversation"]]
        check("the conversation shows messages, replies, proposals and decisions in order",
              "said" in kinds and "reply" in kinds and "proposal" in kinds and "decided" in kinds
              and d["conversation"][-1]["kind"] in ("decided", "proposal", "said"), kinds)
        check("it shows replies only once applied", all(c["status"] == "applied" for c in d["conversation"] if c["kind"] == "reply"))
        check("and what is waiting", [w["action"] for w in d["waiting"]] == [a2], d["waiting"])
    finally:
        srv.shutdown()


if __name__ == "__main__":
    main()
