"""The assistant's experience (S-182), in a throwaway database it drops after (ADMIN_URL from scripts/test.sh). It should:
- record an episode and return its ref; keep the request and response encrypted, readable only with the key
- give the gate (env_gate) record, outcomes and the decider's context (with the latest label of each kind), never
  the text, never a change or a delete
- let the assistant (env_agent) add an outcome, and nothing else here
- keep episodes and outcomes whole; attach outcomes later, the latest of each kind winning
- forget one episode, a time range, or all, with their outcomes; expire by the retention setting; refuse a vague forget

    scripts/test.sh scripts/tests/test_experience.py
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from environment import db as envdb  # noqa: E402
from environment.experience import Experience  # noqa: E402

KEY = "test-only-experience-key"
checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print(("ok  " if ok else "FAIL"), name, "" if ok else detail)


def refused(fn, needle=""):
    try:
        fn()
    except (psycopg.Error, ValueError) as e:
        return needle in str(e)
    return False


def main():
    admin = os.environ["ADMIN_URL"]
    pid = os.getpid()
    name, gate, agent = f"exp_{pid}", f"gate_{pid}", f"agent_{pid}"
    with psycopg.connect(admin, autocommit=True) as a:
        a.execute(f"create database {name}")
    url = admin.rsplit("/", 1)[0] + "/" + name
    host = url.split("@", 1)[1].split("/", 1)[0]
    try:
        with psycopg.connect(url, autocommit=True) as c:
            envdb.migrate(c)
            for login, role in ((gate, "env_gate"), (agent, "env_agent")):
                c.execute(f"create role {login} login password 'test-only'")
                c.execute(f"grant {role} to {login}")
            with psycopg.connect(f"postgresql://{gate}:test-only@{host}/{name}", autocommit=True) as gc, \
                 psycopg.connect(f"postgresql://{agent}:test-only@{host}/{name}", autocommit=True) as ac:
                run(c, gc, ac)
    finally:
        with psycopg.connect(admin, autocommit=True) as a:
            a.execute(f"drop database {name} with (force)")
            a.execute(f"drop role if exists {gate}")
            a.execute(f"drop role if exists {agent}")
    print(f"{sum(checks)}/{len(checks)} checks passed")
    sys.exit(0 if all(checks) else 1)


def run(c, gc, ac):
    owner, g, a = Experience(c, KEY), Experience(gc, KEY), Experience(ac, KEY)
    words = "Remind me to call the dentist on Monday"
    ref = g.record("voice:head", [{"role": "user", "content": words}], "skill:remind", response="Noted.",
                   features={"step": 0, "tools": 6}, embedding=[0.1, 0.2, 0.3], embedder="test", impasse=None,
                   decision={"p": {"skill:remind": 0.93}, "threshold": 0.9}, depended_on=[{"tool": "now"}])
    check("the gate records an episode and gets its ref", len(ref) == 36, ref)
    raw = c.execute("select request, response from env.experience where ref = %s", (ref,)).fetchone()
    check("the request and response are stored encrypted", words.encode() not in bytes(raw[0]) and b"Noted" not in bytes(raw[1]))
    t = owner.text(ref)
    check("the owner reads the text back with the key", t and words in t["request"] and t["response"] == "Noted.", t)
    check("a wrong key reads nothing", refused(lambda: Experience(c, "wrong-key").text(ref)))
    check("recording without a key is refused", refused(lambda: Experience(gc, "").record("voice:head", "x", "fast")))
    check("the gate cannot read the text", refused(lambda: g.text(ref), "permission denied"))
    check("the gate cannot select the table", refused(lambda: gc.execute("select request from env.experience").fetchall(), "permission denied"))
    check("the gate cannot change an episode", refused(lambda: gc.execute("update env.experience set responder = 'fast'"), "permission denied"))
    check("the gate cannot forget", refused(lambda: g.forget(everything=True), "permission denied"))
    check("the owner cannot change an episode either", refused(lambda: c.execute("update env.experience set responder = 'fast'"), "kept whole"))
    check("a bad responder is refused", refused(lambda: g.record("voice:head", "x", "anyone")))
    check("a bad impasse is refused", refused(lambda: g.record("voice:head", "x", "fast", impasse="stuck")))

    ep = g.episodes()
    check("the context has the episode, its features and embedding, no labels yet",
          len(ep) == 1 and ep[0]["ref"] == ref and ep[0]["features"]["step"] == 0 and ep[0]["embedding"] == [0.1, 0.2, 0.3]
          and ep[0]["ok"] is None and ep[0]["outcomes"] == 0, ep)
    check("the context carries no text", not any(words in str(v) for v in ep[0].values()))

    g.outcome(ref, "ok", True, source="task")
    a.outcome(ref, "ok", False, source="owner", note="it was Tuesday")
    a.outcome(ref, "correct", "skill:remind", source="owner")
    g.outcome(ref, "score", 0.5, source="scorer")
    ep = g.episodes()[0]
    check("outcomes attach later; the latest of each kind wins", ep["ok"] is False and ep["correct"] == "skill:remind"
          and ep["score"] == 0.5 and ep["outcomes"] == 4, ep)
    note = c.execute("select note from env.outcome where note is not null").fetchone()[0]
    check("an outcome's note is encrypted", b"Tuesday" not in bytes(note))
    check("a score outside 0..1 is refused", refused(lambda: g.outcome(ref, "score", 2, source="scorer")))
    check("an ok that is not a boolean is refused", refused(lambda: g.outcome(ref, "ok", "yes", source="task")))
    check("an outcome for no episode is refused", refused(lambda: g.outcome("00000000-0000-0000-0000-000000000000", "ok", True, "task"), "no episode"))
    check("the assistant cannot read the context", refused(lambda: a.episodes(), "permission denied"))
    check("the assistant cannot record", refused(lambda: a.record("worker:loop", "x", "slow"), "permission denied"))
    check("an outcome cannot be deleted", refused(lambda: c.execute("delete from env.outcome"), "kept whole"))

    # forgetting: one, a range, all; retention
    old = g.record("worker:loop", "old one", "slow")
    c.execute("set session_replication_role = replica")      # the owner backdates for the test only (triggers off)
    c.execute("update env.experience set at = now() - interval '40 days' where ref = %s", (old,))
    c.execute("set session_replication_role = origin")
    mid = g.record("worker:loop", "middle", "fast")
    g.outcome(mid, "ok", True, "task")
    check("caller and since filter the context", [e["ref"] for e in g.episodes(caller="worker:loop", since=datetime.now(timezone.utc) - timedelta(days=1))] == [mid])
    check("a vague forget is refused", refused(lambda: owner.forget(), "say what to forget"))
    check("forgetting one episode removes it and its outcomes", owner.forget(ref=mid) == 1
          and c.execute("select count(*) from env.outcome o join env.experience e on e.id = o.episode where e.ref = %s", (mid,)).fetchone()[0] == 0
          and mid not in [e["ref"] for e in owner.episodes()])
    check("no retention set: nothing expires", owner.expire() == 0)
    c.execute("select env.set('experience', 'retention_days', '30', 'owner')")
    check("retention expires what is older", owner.expire() == 1 and old not in [e["ref"] for e in owner.episodes()])
    r2 = g.record("worker:loop", "today", "slow")
    now = datetime.now(timezone.utc)
    check("forgetting a time range", owner.forget(start=now - timedelta(hours=1), end=now + timedelta(hours=1)) == 2
          and owner.episodes() == [], r2)
    g.record("worker:loop", "again", "slow")
    check("forgetting everything", owner.forget(everything=True) == 1 and c.execute("select count(*) from env.outcome").fetchone()[0] == 0)


if __name__ == "__main__":
    main()
