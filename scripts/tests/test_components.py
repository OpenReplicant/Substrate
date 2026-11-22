"""Components, the judge and the loop between them (S-151), in a throwaway database it drops after (ADMIN_URL from
scripts/test.sh). It should:
- keep every version of a component with its card, at most one active per name
- let an author (env_agent) submit a version and read only the training slice of the record; never claim one for
  judging, record a verdict, activate, or read the verdicts or the record
- let the judge (env_judge) claim a proposed version, record one verdict (kept whole), and file the activation as
  a proposal; never activate it itself
- hold out a fixed third of the record from authors, the same third every time
- activate only what the judge found better (or a first version, as the seed), retiring the incumbent
- decide the outcome as voice/reply.py's KPIs and environment/judge.py's rule say; tell a spoken reply from one
  that is not fit to speak, and find the handoff line

    scripts/test.sh scripts/tests/test_components.py
"""
import json
import os
import sys
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from environment import db as envdb  # noqa: E402
from environment import Env  # noqa: E402
from environment import companion as comp  # noqa: E402
from environment.judge import outcome  # noqa: E402
from voice import reply  # noqa: E402

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
    pid = os.getpid()
    name, author, judge = f"comp_lc_{pid}", f"author_{pid}", f"judge_{pid}"
    with psycopg.connect(admin, autocommit=True) as a:
        a.execute(f"create database {name}")
    url = admin.rsplit("/", 1)[0] + "/" + name
    host = url.split("@", 1)[1].split("/", 1)[0]
    try:
        with psycopg.connect(url, autocommit=True) as c:
            envdb.migrate(c)
            for login, role in ((author, "env_agent"), (judge, "env_judge")):
                c.execute(f"create role {login} login password 'test-only'")
                c.execute(f"grant {role} to {login}")
            owner = Env(c)
            comp.setup(owner, author)
            with psycopg.connect(f"postgresql://{author}:test-only@{host}/{name}", autocommit=True) as ac, \
                 psycopg.connect(f"postgresql://{judge}:test-only@{host}/{name}", autocommit=True) as jc:
                run(c, owner, ac, jc)
        pure()
    finally:
        with psycopg.connect(admin, autocommit=True) as a:
            a.execute(f"drop database {name} with (force)")
            a.execute(f"drop role if exists {author}")
            a.execute(f"drop role if exists {judge}")
    print(f"{sum(checks)}/{len(checks)} checks passed")
    sys.exit(0 if all(checks) else 1)


def run(c, owner: Env, ac, jc):
    seed = c.execute("select id, version, status from env.component where name = %s", (reply.NAME,)).fetchall()
    check("setup seeds the reply component as its active first version", len(seed) == 1 and seed[0][1:] == (1, "active"), seed)
    # the record: voice turns, a third of them held out
    ids = []
    for i in range(30):
        h = owner.publish("companion.voice.heard", {"text": f"utterance {i}"}, "owner (voice)")
        owner.publish("companion.voice.said", {"text": f"reply {i}", "heard": h, "component": seed[0][0], "first_audio_ms": 900}, "voice head")
        ids.append(h)
    held = [i for i in ids if c.execute("select env.held_out(%s)", (i,)).fetchone()[0]]
    seen = [r[0] for r in ac.execute("select heard_id from env.training_turns('companion', 100)").fetchall()]
    check("about a third of the record is held out", 4 <= len(held) <= 16, len(held))
    check("the author's training slice leaves out every held-out turn", seen and not set(seen) & set(held) and set(seen) | set(held) == set(ids),
          (len(seen), len(held)))
    check("the split is the same every time", held == [i for i in ids if c.execute("select env.held_out(%s)", (i,)).fetchone()[0]])
    pair = ac.execute("select heard, said from env.training_turns('companion', 1)").fetchone()
    check("a training turn pairs what was heard with what was said back", pair and pair[1] and pair[0].split()[-1] == pair[1].split()[-1], pair)
    # the author submits
    card = {**reply.SEED, "rationale": "test"}
    cid = ac.execute("select env.submit_component('companion', %s, %s, 'author test')", (reply.NAME, Jsonb(card))).fetchone()[0]
    row = c.execute("select version, status, against, login from env.component where id = %s", (cid,)).fetchone()
    check("an author submits a new version, against the active one", row[:3] == (2, "proposed", seed[0][0]) and row[3].startswith("author_"), row)
    check("an author cannot claim it for judging", refused(lambda: ac.execute("select env.claim_component()"), "permission denied"))
    check("an author cannot record a verdict", refused(lambda: ac.execute("select env.record_verdict(%s, 'better', '{}', '{}', '{}', 'me')", (cid,)), "permission denied"))
    check("an author cannot activate", refused(lambda: ac.execute("select env.activate(%s, 'owner')", (cid,)), "permission denied"))
    check("an author cannot read verdicts", refused(lambda: ac.execute("select * from env.verdict"), "permission denied"))
    check("an author cannot read the record", refused(lambda: ac.execute("select * from env.signal"), "permission denied"))
    check("an author cannot change a component", refused(lambda: ac.execute("update env.component set status = 'active'"), "permission denied"))
    check("a version not yet judged cannot be activated", refused(lambda: owner.c.execute("select env.activate(%s, 'owner')", (cid,)), "only one the judge"))
    # the judge
    got = jc.execute("select env.claim_component()").fetchone()[0]
    check("the judge claims the proposed version", got == cid and c.execute("select status from env.component where id = %s", (cid,)).fetchone()[0] == "judging")
    check("and nothing else is waiting", jc.execute("select env.claim_component()").fetchone()[0] is None)
    check("the judge reads held-out turns", jc.execute("select count(*) from env.signal where key = 'companion.voice.heard' and env.held_out(id)").fetchone()[0] == len(held))
    vid = jc.execute("select env.record_verdict(%s, 'better', %s, %s, '{}', 'judge test')", (cid, Jsonb({"k": 1}), Jsonb({"labelled": 30}))).fetchone()[0]
    check("a better verdict leaves the version judged", c.execute("select status from env.component where id = %s", (cid,)).fetchone()[0] == "judged")
    check("a verdict is recorded once", refused(lambda: jc.execute("select env.record_verdict(%s, 'worse', '{}', '{}', '{}', 'judge')", (cid,)), "not being judged"))
    check("and kept whole", refused(lambda: c.execute("update env.verdict set outcome = 'worse' where id = %s", (vid,)), "kept whole"))
    check("the judge cannot activate", refused(lambda: jc.execute("select env.activate(%s, 'judge')", (cid,)), "permission denied"))
    a, st = Env(jc).act("companion.activate", {"component": cid}, "judge test")
    check("the judge files the activation as a proposal", st == "proposed")
    check("the judge cannot decide it", refused(lambda: jc.execute("select env.decide(%s, true, 'owner')", (a,)), "permission denied"))
    owner.decide(a, True, "owner")
    for m in owner.read("act_companion_activate", 30, 5):
        comp.apply(owner, "activate", m)
    rows = dict(c.execute("select id, status from env.component where name = %s", (reply.NAME,)).fetchall())
    check("approved by the owner, it is active and the incumbent retired", rows == {seed[0][0]: "retired", cid: "active"}, rows)
    who = c.execute("select status_by from env.component where id = %s", (cid,)).fetchone()[0]
    check("the record names who activated it", who == "owner", who)
    check("the author reads the active card", ac.execute("select version from env.active_component('companion', %s)", (reply.NAME,)).fetchone()[0] == 2)
    # a refused one
    cid3 = ac.execute("select env.submit_component('companion', %s, %s, 'author test')", (reply.NAME, Jsonb(card))).fetchone()[0]
    jc.execute("select env.claim_component()")
    jc.execute("select env.record_verdict(%s, 'same', '{}', '{}', '{}', 'judge')", (cid3,))
    check("no measurable difference refuses it", c.execute("select status from env.component where id = %s", (cid3,)).fetchone()[0] == "refused")
    check("and it cannot be activated", refused(lambda: c.execute("select env.activate(%s, 'owner')", (cid3,)), "only one the judge"))
    check("there is never more than one active version",
          refused(lambda: c.execute("update env.component set status = 'active' where id = %s", (cid3,)), "component_one_active"))


def pure():
    inc = {"handoff_agreement": 0.8, "spoken_form": 0.9, "first_token_ms": 500}
    check("better on handoffs by more than one case is better", outcome({**inc, "handoff_agreement": 0.9}, inc, 1.0, 30, 40) == "better")
    check("within one case is the same", outcome({**inc, "handoff_agreement": 0.83}, inc, 1.0, 30, 40) == "same")
    one = {"handoff_agreement": 28 / 30, "spoken_form": 1.0, "first_token_ms": 398}
    check("exactly one case better is the same (verdict 1's case: 29/30 against 28/30)",
          outcome({**one, "handoff_agreement": 29 / 30, "first_token_ms": 384}, one, 1.0, 30, 40) == "same")
    check("two cases better is better", outcome({**one, "handoff_agreement": 30 / 30}, one, 1.0, 30, 40) == "better")
    check("worse on handoffs is worse", outcome({**inc, "handoff_agreement": 0.7}, inc, 1.0, 30, 40) == "worse")
    check("much slower is worse, however good", outcome({**inc, "handoff_agreement": 1.0, "first_token_ms": 900}, inc, 1.0, 30, 40) == "worse")
    check("failing its own tests is worse", outcome({**inc, "handoff_agreement": 1.0}, inc, 0.5, 30, 40) == "worse")
    check("a plain reply is fit to speak", reply.spoken_ok("Sure, I can do that. It's twenty past four."))
    check("a list is not", not reply.spoken_ok("Here you go:\n- one\n- two"))
    check("markdown is not", not reply.spoken_ok("That is **important**."))
    check("four sentences are too many", not reply.spoken_ok("One. Two. Three. Four."))
    check("the handoff line is found", reply.split("I'll hand that over.\nHANDOFF: check the disk") == ("I'll hand that over.", "check the disk"))
    check("and none when there is none", reply.split("Hello there.") == ("Hello there.", None))
    check("the seed card's params are kept in bounds", reply.params({"params": {"history_turns": 99, "max_tokens": 5}})["history_turns"] == 40)


if __name__ == "__main__":
    main()
