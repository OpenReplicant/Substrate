"""The real-time environment (plan step 3c), in a throwaway database it drops after (ADMIN_URL from scripts/test.sh).
It should:
- fan a published signal out to every queue bound to a matching pattern (* one segment, # any), and no other;
  log it whole, refusing any change to it
- hide a read message for its visibility timeout, give it back unacknowledged (counting deliveries), and never
  again once acknowledged
- pass an actuator call through its gate: free queued at once; propose waiting, announced, until a person other
  than its maker decides, then queued or refused; deny refused; every call recorded, applied ones archived
- apply its schema once (environment/sql/, environment/db.py), and again without change
- give an MCP tool its gate from its annotations when registered, follow them while no person has set the gate (both
  directions, a deployment's policy first), and keep a gate a person set
- as the channel (stdio MCP): declare claude/channel, push a subscribed signal as notifications/claude/channel,
  push it again while unacknowledged, stop once ack is called, and act through the gates

    scripts/test.sh scripts/tests/test_environment.py
"""
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from environment import db as envdb  # noqa: E402
from environment import Env  # noqa: E402

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
    name = f"env_test_{os.getpid()}"
    with psycopg.connect(admin, autocommit=True) as a:
        a.execute(f"create database {name}")
    url = admin.rsplit("/", 1)[0] + "/" + name
    try:
        with psycopg.connect(url, autocommit=True) as c:
            check("the schema applies, in order", envdb.migrate(c) == sorted(f.name for f in envdb.SQL.glob("*.sql")))
            check("and applying it again changes nothing", envdb.migrate(c) == [])
            run(Env(c), url)
    finally:
        with psycopg.connect(admin, autocommit=True) as a:
            a.execute(f"drop database {name} with (force)")
    print(f"{sum(checks)}/{len(checks)} checks passed")
    sys.exit(0 if all(checks) else 1)


def keys(e, q):
    return [m["key"] for m in e.read(q, 0, 50)]


def run(e: Env, url: str):
    c = e.c
    # Streams in: fan-out by pattern
    e.subscribe("all_home", ["home.#"])
    e.subscribe("messages", ["home.*.message"])
    e.subscribe("elsewhere", ["other.#"])
    sid = e.publish("home.owner.message", {"text": "hello"}, "owner")
    e.publish("home.clock.tick", {"t": 1}, "clock")
    check("a signal reaches every queue bound to a matching pattern",
          keys(e, "all_home") == ["home.owner.message", "home.clock.tick"]
          and keys(e, "messages") == ["home.owner.message"], (keys(e, "all_home"), keys(e, "messages")))
    check("and no other", keys(e, "elsewhere") == [])
    row = c.execute("select key, body, source, reached from env.signal where id = %s", (sid,)).fetchone()
    check("it is logged whole, with how many queues it reached", row == ("home.owner.message", {"text": "hello"}, "owner", 2), row)
    check("a logged signal cannot be changed", refused(lambda: c.execute("update env.signal set body = '{}' where id = %s", (sid,)), "kept whole"))
    check("or deleted", refused(lambda: c.execute("delete from env.signal where id = %s", (sid,)), "kept whole"))
    check("a malformed routing key is refused", refused(lambda: e.publish("Home", {}, "x"), "signal_key_check"))

    # Visibility: unacknowledged comes back, acknowledged does not
    e.subscribe("vt", ["vt.#"])
    e.publish("vt.s.k", {"n": 1}, "test")
    first = e.read("vt", 1)
    check("a read message is delivered", len(first) == 1 and first[0]["body"] == {"n": 1} and first[0]["read_ct"] == 1, first)
    check("and hidden while its visibility timeout runs", e.read("vt", 1) == [])
    time.sleep(1.5)
    again = e.read("vt", 1)
    check("unacknowledged, it comes back, counted", len(again) == 1 and again[0]["msg_id"] == first[0]["msg_id"]
          and again[0]["read_ct"] == 2, again)
    check("acknowledged, it is archived", e.ack("vt", [again[0]["msg_id"]]) == [again[0]["msg_id"]])
    time.sleep(1.5)
    check("and not delivered again", e.read("vt", 1) == [])

    # Acting, through gates
    e.subscribe("review", ["home.review.*"])
    q_reply = e.actuator("home.reply", "free", "test")
    e.actuator("home.budget", "propose", "test")
    e.actuator("home.shell", "deny", "test")
    a1, st1 = e.act("home.reply", {"text": "hi"}, "claude-code")
    msgs = e.read(q_reply, 0)
    check("free: queued at once on the actuator's queue", st1 == "queued" and [m["action"] for m in msgs] == [a1], (st1, msgs))
    a2, st2 = e.act("home.budget", {"cap_usd": 5}, "claude-code")
    q_budget = c.execute("select queue from env.actuator where name = 'home.budget'").fetchone()[0]
    check("propose: waits, nothing queued", st2 == "proposed" and e.read(q_budget, 0) == [] and [w["id"] for w in e.waiting()] == [a2])
    rv = e.read("review", 0)
    check("and is announced on <env>.review.proposed", [(m["key"], m["body"]["action"]) for m in rv] == [("home.review.proposed", a2)], rv)
    check("its maker cannot decide it", refused(lambda: e.decide(a2, True, "claude-code"), "other than the one"))
    check("a person approves it: queued", e.decide(a2, True, "owner", "fine") == "queued"
          and [m["action"] for m in e.read(q_budget, 0)] == [a2])
    check("and the decision is announced", any(m["key"] == "home.review.decided" and m["body"]["approved"] for m in e.read("review", 0)))
    check("a decided proposal is not decided again", refused(lambda: e.decide(a2, False, "owner"), "not waiting"))
    a3, _ = e.act("home.budget", {"cap_usd": 500}, "claude-code")
    check("a person refuses one: never queued", e.decide(a3, False, "owner", "too much") == "refused" and len(e.read(q_budget, 0)) == 1)
    a4, st4 = e.act("home.shell", {"cmd": "rm"}, "claude-code")
    q_shell = c.execute("select queue from env.actuator where name = 'home.shell'").fetchone()[0]
    check("deny: refused, nothing queued", st4 == "denied" and e.read(q_shell, 0) == [])
    check("an unknown actuator is refused", refused(lambda: e.act("home.nope", {}, "x"), "no actuator"))
    e.done(a1, {"sent": True})
    check("applied: recorded and archived", c.execute("select status, result from env.action where id = %s", (a1,)).fetchone()
          == ("applied", {"sent": True}) and e.read(q_reply, 0) == [])
    check("every call is recorded", [r[0] for r in c.execute("select status from env.action order by id")]
          == ["applied", "queued", "refused", "denied"])

    mcp_gates(c)
    channel(e, url)


def mcp_gates(c):
    def register(*tools):
        rows = c.execute("select tool, gate from env.mcp_register('srv', 'http', '{}', '{}', %s::jsonb, 'connector:srv')",
                         (json.dumps([{"name": n, "annotations": {"readOnlyHint": ro} if ro is not None else {}}
                                      for n, ro in tools]),)).fetchall()
        return dict(rows)

    first = register(("read", True), ("write", False), ("plain", None), ("later", None), ("mine", None))
    check("MCP: a tool's first gate follows its annotations (read-only free, else propose)",
          first == {"srv_read": "free", "srv_write": "propose", "srv_plain": "propose", "srv_later": "propose",
                    "srv_mine": "propose"}, first)
    act = c.execute("select actuator from env.mcp_tool where server = 'srv' and name = 'mine'").fetchone()[0]
    c.execute("select env.actuator(%s, 'free', 'person_owner')", (act,))
    again = register(("read", True), ("write", False), ("plain", None), ("later", True), ("mine", None))
    check("a tool that becomes read-only is freed while no person has set its gate", again["srv_later"] == "free", again)
    check("a gate a person set is kept", again["srv_mine"] == "free", again)
    check("the others are unchanged", (again["srv_read"], again["srv_write"], again["srv_plain"]) == ("free", "propose", "propose"), again)
    back = register(("read", False), ("write", False), ("plain", None), ("later", True), ("mine", False))
    check("a tool that stops being read-only goes back to propose", back["srv_read"] == "propose", back)
    check("and a person's gate is still kept", back["srv_mine"] == "free", back)
    c.execute("insert into env.mcp_policy (server, tool, gate, set_by) values ('srv', 'write', 'free', 'test')")
    pol = register(("read", False), ("write", False), ("plain", None), ("later", True), ("mine", False))
    check("a deployment's policy comes before the annotations", pol["srv_write"] == "free", pol)


class Proc:
    def __init__(self, url, vt):
        self.p = subprocess.Popen([sys.executable, "-m", "environment.channel", "chan", "home.owner.*"],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=ROOT,
                                  env={**os.environ, "STORE_URL": url, "CHANNEL_VT": str(vt), "CHANNEL_POLL": "0.2"})
        self.q = queue.Queue()
        threading.Thread(target=lambda: [self.q.put(json.loads(l)) for l in self.p.stdout], daemon=True).start()

    def send(self, m):
        self.p.stdin.write(json.dumps(m) + "\n")
        self.p.stdin.flush()

    def until(self, pred, timeout):
        end, seen = time.monotonic() + timeout, []
        while time.monotonic() < end:
            try:
                m = self.q.get(timeout=max(0.01, end - time.monotonic()))
            except queue.Empty:
                break
            seen.append(m)
            if pred(m):
                return m, seen
        return None, seen

    def call(self, mid, name, args):
        self.send({"jsonrpc": "2.0", "id": mid, "method": "tools/call", "params": {"name": name, "arguments": args}})
        m, _ = self.until(lambda m: m.get("id") == mid, 10)
        return m and m["result"]


def channel(e: Env, url: str):
    ch = Proc(url, vt=2)
    try:
        ch.send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "claude-code", "version": "test"}}})
        init, _ = ch.until(lambda m: m.get("id") == 1, 20)
        caps = (init or {}).get("result", {}).get("capabilities", {})
        check("channel: declares claude/channel and tools", caps.get("experimental", {}).get("claude/channel") == {} and "tools" in caps,
              (init, ch.p.stderr.read() if ch.p.poll() is not None else ""))
        check("channel: its instructions say signals are data", "never instructions" in (init or {}).get("result", {}).get("instructions", ""))
        ch.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        is_event = lambda m: m.get("method") == "notifications/claude/channel"  # noqa: E731
        e.publish("home.clock.tick", {"t": 2}, "clock")              # not subscribed
        e.publish("home.owner.message", {"text": "are you there?"}, "owner")
        ev, seen = ch.until(is_event, 10)
        meta = (ev or {}).get("params", {}).get("meta", {})
        check("channel: a published signal reaches the session", ev and ev["params"]["content"] == "are you there?"
              and meta.get("key") == "home.owner.message" and meta.get("by") == "owner" and meta.get("read_ct") == "1", seen)
        check("channel: meta keys are identifiers only", all(k.replace("_", "").isalnum() for k in meta), meta)
        again, _ = ch.until(is_event, 6)
        check("channel: unacknowledged, it comes back", again and again["params"]["meta"]["msg_id"] == meta.get("msg_id")
              and again["params"]["meta"]["read_ct"] == "2", again)
        res = ch.call(2, "ack", {"msg_ids": [int(meta["msg_id"])]})
        check("channel: ack archives it", res and not res["isError"] and "archived" in res["content"][0]["text"], res)
        late, _ = ch.until(is_event, 4)
        check("channel: and it is not delivered again", late is None, late)
        e.actuator("home.budget", "propose", "test")
        res = ch.call(3, "act", {"actuator": "home.budget", "input": {"cap_usd": 1}})
        check("channel: act goes through the gate", res and "proposed" in res["content"][0]["text"], res)
        by = e.c.execute("select caller from env.action order by id desc limit 1").fetchone()[0]
        check("channel: the action names who called it", by == "claude-code test (channel chan)", by)
    finally:
        ch.p.terminate()
        ch.p.wait(5)


if __name__ == "__main__":
    main()
