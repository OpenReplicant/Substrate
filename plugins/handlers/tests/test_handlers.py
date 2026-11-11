"""handlers:declare and handlers:run in a throwaway database (README.md, "Check"). The review lane holds five gaps one
extractor raised: two of a kind that a person decided, one withdrawn, one still open, one of a kind never seen.
A file holds two hook runs. The run should:
- answer from precedent only where an earlier decision exists
- score that answer against the person's decision
- give the review lane a person's cost, and rank it above the hook and the rule
- attribute each call's values to its handler
- change nothing when replayed
- pick up a decision made later

    WORKBENCH_ADMIN_URL=postgresql://postgres:...@127.0.0.1:5432/postgres python3 plugins/handlers/tests/test_handlers.py
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "workbench"), str(ROOT / "plugins/handlers")]
os.environ["WORKBENCH_DB"] = DB = f"workbench_test_{os.getpid()}"
os.environ.setdefault("WORKBENCH_JWT_SECRET", "h-" + "z" * 40)

import psycopg  # noqa: E402
from psycopg import sql  # noqa: E402

from workbench import cli  # noqa: E402
from workbench.extract import Plugins, run_extractor  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print(("ok  " if ok else "FAIL"), name, "" if ok else detail)


STREAMS = """streams:
  gaps:
    title: A drift checker's gaps
    source: {kind: decisions, raised_by: "x:drift", decision_kind: gap}
    answers: advisory
    outcome: the person's decision in the review lane
    handlers:
      precedent: {kind: rule}
      review-lane: {kind: person}
      broken: {kind: rule, entry: nobody-registered-this}
  hooks:
    source: {kind: jsonl, path: calls.jsonl}
    handlers:
      posttooluse-map: {kind: hook, component: posttooluse-map}
"""

GAPS = [  # key, status, decided_by, minutes after the first, minutes to decide
    ("undeclared:volume:a", "declined", "owner", 0, 30),
    ("undeclared:volume:b", "declined", "owner", 60, 5),
    ("undeclared:volume:c", "approved", "owner", 120, 10),     # precedent says declined: wrong, and scored so
    ("undeclared:skill:x", "withdrawn", "x:drift", 130, 1),
    ("undeclared:api:y", "open", None, 140, None),
    ("undeclared:skill:x", "declined", "owner", 150, 2),       # the same key raised again after it closed: a new input
]


def q(conn, text, *args):
    return conn.execute(text, args).fetchall()


try:
    with tempfile.TemporaryDirectory() as d:
        Path(d, "streams.yaml").write_text(STREAMS)
        now = time.time()
        Path(d, "calls.jsonl").write_text(
            json.dumps({"stream": "hooks", "handler": "posttooluse-map", "started": now - 10, "seconds": 2.5, "exit": 0}) + "\n"
            + json.dumps({"stream": "hooks", "handler": "posttooluse-map", "started": now - 5, "seconds": 1.5, "exit": 1, "note": "no tools"}) + "\n")
        os.environ["WB_HANDLERS_ROOT"] = d
        cli.migrate()
        cli.load_plugin(ROOT / "plugins/handlers")
        plugins = Plugins().load(ROOT / "plugins")
        with cli.connect() as conn:
            for key, status, by, at, took in GAPS:
                conn.execute("""insert into wb.decision (kind, key, raised_by, subject, status, decided_by, decided_at, created_at)
                                values ('gap', %s, 'x:drift', '{}', %s, %s,
                                        case when %s::int is null then null else now() - interval '1 day' + make_interval(mins => %s + %s) end,
                                        now() - interval '1 day' + make_interval(mins => %s))""",
                             (key, status, by, took, at, took or 0, at))
        r = run_extractor(cli.connect, plugins, "handlers:declare", {"file": "streams.yaml"})
        check("declare runs", r.get("ok"), r)
        r = run_extractor(cli.connect, plugins, "handlers:run", {})
        check("run runs", r.get("ok"), r)

        with cli.connect() as conn:
            calls = {s: (k, v, c, cor, cost, rs) for s, k, v, c, cor, cost, rs in q(conn,
                     "select handler || ' ' || split_part(input, '-', 4), kind, value, confidence, correct, cost, reason from api.call where stream = 'gaps'")}
            n = len(q(conn, "select 1 from api.input where stream = 'gaps'"))
            check("one input per decision, a key raised twice included", n == 6, n)
            check("precedent escalates where nothing like it was decided before",
                  calls["precedent a"][0] == "escalate" and "no earlier" in calls["precedent a"][5], calls.get("precedent a"))
            check("and answers from the earlier decision where one was",
                  calls["precedent b"][:2] == ("answer", "declined") and calls["precedent b"][2] == 0.5, calls.get("precedent b"))
            check("its answer is scored against the person's decision: right once, wrong once",
                  calls["precedent b"][3] is True and calls["precedent c"][3] is False, (calls.get("precedent b"), calls.get("precedent c")))
            check("the review lane's answer is the decision, with a person's cost and the time it took",
                  calls["review-lane a"][:2] == ("answer", "declined") and calls["review-lane a"][4] == {"person": 1, "usd": 0, "seconds": 1800},
                  calls.get("review-lane a"))
            check("a withdrawn gap is dropped, an open one waits",
                  calls["review-lane y"][0] == "waiting", calls.get("review-lane y"))
            x = sorted(k for (k,) in q(conn, "select kind from api.call where handler = 'review-lane' and input like '%%skill-x%%'"))
            check("a withdrawn gap is dropped; the same key raised again is its own input", x == ["answer", "dropped"], x)
            check("a handler no one registered is refused on every input, and the input goes on up",
                  all(calls[f"broken {k}"][0] == "refused" for k in "abcy"), [calls.get(f"broken {k}") for k in "abcy"])
            authors = {a for (a,) in q(conn, """select distinct cl.author from wb.claim cl join content.call c on c.id = cl.subject_id
                                                where c.handler = 'precedent' and cl.field = 'kind'""")}
            check("a call's values are claims attributed to its handler", authors == {"handler:precedent"}, authors)
            live = q(conn, """select count(*) filter (where cl.status = 'current'), count(*) from wb.claim cl
                              join content.call c on c.id = cl.subject_id where cl.author like 'handler:%%'""")[0]
            check("and they stay current when the run finishes (not taken for statements it stopped making)",
                  live[0] == live[1] and live[1] > 0, live)
            within = q(conn, """select count(distinct r.id) from wb.run r join wb.claim cl on cl.run_id = r.id
                                where cl.author like 'handler:%%' and r.extractor = cl.author and r.inputs ? 'within'""")[0][0]
            check("under a run of the handler's own, within the extractor's", within >= 2, within)
            scorer = {a for (a,) in q(conn, """select distinct cl.author from wb.claim cl join content.call c on c.id = cl.subject_id
                                               where cl.field = 'correct' and cl.status = 'current'""")}
            check("its score is the run's, not the handler's", scorer == {"handlers:run"}, scorer)
            hooks = q(conn, "select kind from api.call where stream = 'hooks' order by at")
            check("hook runs recorded outside the runner come in as calls: exit 0 answers, anything else escalates",
                  [k for (k,) in hooks] == ["answer", "escalate"], hooks)
            ranks = dict(q(conn, "select slug, rank from api.handler"))
            measured = dict(q(conn, "select slug, measured from api.handler"))
            check("ranks come from measured cost: the rule below the hook, the person at the top",
                  ranks["precedent"] < ranks["posttooluse-map"] < ranks["review-lane"] and max(ranks.values()) == ranks["review-lane"]
                  and measured["precedent"] and measured["review-lane"], (ranks, measured))
            route = q(conn, "select ladder from api.route where stream = 'gaps'")
            check("the stream's route is its handlers in rank order", route and route[0][0][-1] == "review-lane", route)
            hs = dict(q(conn, "select slug, jsonb_build_object('scored', scored, 'correct', correct) from api.handler"))
            check("a handler's counts say how often its answers were right", hs["precedent"] == {"scored": 2, "correct": 1}, hs)
            before = q(conn, "select count(*) from wb.claim")[0][0]

        r = run_extractor(cli.connect, plugins, "handlers:run", {})
        with cli.connect() as conn:
            after = q(conn, "select count(*) from wb.claim")[0][0]
        check("a replay with nothing new changes nothing", r.get("ok") and after == before, (r, before, after))
        with cli.connect() as conn:
            still = q(conn, "select count(*) from wb.claim where author like 'handler:%%' and status <> 'current'")[0][0]
        check("and keeps the handlers' claims current", still == 0, still)

        with cli.connect() as conn:
            conn.execute("update wb.decision set status = 'declined', decided_by = 'owner', decided_at = now() where key = 'undeclared:api:y'")
        run_extractor(cli.connect, plugins, "handlers:run", {})
        with cli.connect() as conn:
            y = q(conn, "select kind, value from api.call where handler = 'review-lane' and input like '%%api-y-%%'")
            st = q(conn, "select status, resolved_by from api.input where key = 'undeclared:api:y'")
        check("a decision made later is picked up: the waiting call answers", y == [("answer", "declined")], y)
        check("and the input is resolved by the person", st == [("resolved", "review-lane")], st)
finally:
    with psycopg.connect(cli.url("postgres"), autocommit=True) as conn:
        conn.execute(sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(DB)))

print(f"{sum(checks)}/{len(checks)} checks passed")
sys.exit(0 if all(checks) else 1)
