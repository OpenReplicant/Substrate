"""W3 checks (BRIEF.md section 9): extractors write with evidence through the same rules, a run is all or
nothing, decisions are raised and withdrawn, changes are announced, and the server checks tokens as PostgREST does.

    WORKBENCH_ADMIN_URL=postgresql://postgres:...@127.0.0.1:5432/postgres python3 tests/test_w3.py
"""
import base64
import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
DB = f"workbench_test_{os.getpid()}"
os.environ["WORKBENCH_DB"] = DB
os.environ["WORKBENCH_JWT_SECRET"] = "w3-secret-" + "y" * 32

import psycopg  # noqa: E402
from psycopg import sql  # noqa: E402

from workbench import cli  # noqa: E402
from workbench.extract import Plugins, run_extractor  # noqa: E402
from workbench.server import verify  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print(("ok  " if ok else "FAIL"), name, "" if ok else detail)


def token(claims, secret=os.environ["WORKBENCH_JWT_SECRET"]):
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")  # noqa: E731
    h, p = enc({"alg": "HS256", "typ": "JWT"}), enc(claims)
    s = base64.urlsafe_b64encode(hmac.new(secret.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()).decode().rstrip("=")
    return f"{h}.{p}.{s}"


try:
    cli.migrate()
    cli.load_plugin(HERE / "fixtures/plugin")
    plugins = Plugins().load(HERE / "fixtures")
    check("a plugin's server module registers its extractor", "fixture:notes" in plugins.extractors, plugins.loaded)
    listener = psycopg.connect(cli.url(DB), autocommit=True)
    listener.execute("listen wb_events")

    r1 = run_extractor(cli.connect, plugins, "fixture:notes", {"text": "a: first\nb: second", "flag": "a"})
    check("a run writes its items", r1["ok"] and r1["items"] == 2, r1)
    with cli.connect() as conn:
        rows = conn.execute("select c.field, c.author, c.quote, c.span, s.uri, c.run_id::text from wb.claim c"
                            " join content.note n on n.id = c.subject_id left join wb.source s on s.id = c.source_id"
                            " where n.slug = 'a' and c.field = 'body'").fetchall()
        check("an extractor's claim carries its author, source, quote and span",
              rows and rows[0][1] == "fixture:notes" and rows[0][2] == "a: first" and rows[0][3] == {"start_line": 1, "end_line": 1}
              and rows[0][4] == "memory:notes.txt" and rows[0][5] == r1["run"], rows)
        by = conn.execute("select created_by from content.note where slug = 'a'").fetchone()[0]
        check("the item says the extractor made it", by == "fixture:notes", by)
        n_claims = conn.execute("select count(*) from wb.claim").fetchone()[0]
    r2 = run_extractor(cli.connect, plugins, "fixture:notes", {"text": "a: first\nb: second", "flag": "a"})
    with cli.connect() as conn:
        again = conn.execute("select count(*) from wb.claim").fetchone()[0]
        runs = conn.execute("select count(*) from wb.run where ended_at is not null").fetchone()[0]
        opened = conn.execute("select count(*) from wb.decision where status = 'open'").fetchone()[0]
    check("re-reading an unchanged source adds no claims", r2["ok"] and again == n_claims, (n_claims, again))
    check("each run is recorded", runs == 2, runs)
    check("raising the same decision again is a no-op", opened == 1, opened)

    r3 = run_extractor(cli.connect, plugins, "fixture:notes", {"text": "a: changed"})
    with cli.connect() as conn:
        a = conn.execute("select c.value, c.status from wb.claim c join content.note n on n.id = c.subject_id"
                         " where n.slug = 'a' and c.field = 'body' order by c.observed_at").fetchall()
        b = conn.execute("select count(*) from wb.claim c join content.note n on n.id = c.subject_id"
                         " where n.slug = 'b' and c.status = 'current'").fetchone()[0]
        b_row = conn.execute("select count(*) from content.note where slug = 'b'").fetchone()[0]
        dec = conn.execute("select status, decided_by, note from wb.decision").fetchall()
    check("a changed value supersedes the extractor's earlier claim", [s for _, s in a] == ["superseded", "current"]
          and a[-1][0] == "changed", a)
    check("what the source no longer says is retracted, and the item stays", b == 0 and b_row == 1, (b, b_row))
    check("a decision no longer found is withdrawn by its raiser", dec == [("withdrawn", "fixture:notes", "no longer found")], dec)

    bad = run_extractor(cli.connect, plugins, "fixture:notes", {"fail": "1"})
    with cli.connect() as conn:
        doomed = conn.execute("select count(*) from content.note where slug = 'doomed'").fetchone()[0]
        failed = conn.execute("select outcome->>'ok' from wb.run where outcome->>'ok' = 'false'").fetchall()
    check("a failed run keeps none of its writes, and is recorded as failed", not bad["ok"] and doomed == 0 and len(failed) == 1, bad.get("error"))

    time.sleep(0.2)
    kinds = {}
    for note in listener.notifies(timeout=1, stop_after=200):
        e = json.loads(note.payload)
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
        if e["kind"] == "item":
            check_item = e
    listener.close()
    check("writes, runs and decisions are announced", kinds.get("item") and kinds.get("run") and kinds.get("decision"), kinds)
    check("an announcement names what changed, not its content", set(check_item) == {"kind", "type", "id", "op", "author"}, check_item)

    # relations say who stated them; a run replaces only its own, and done() drops its own from items gone
    rel = lambda: {(r[0], r[1], r[2]) for r in cli.connect().execute(  # noqa: E731
        "select f.slug || '>' || t.slug, r.predicate, r.author from wb.relation r join content.note f on f.id = r.from_id"
        " join content.note t on t.id = r.to_id").fetchall()}
    run_extractor(cli.connect, plugins, "fixture:notes", {"text": "a: one\nb: two", "link": "a>b,b>a"})
    run_extractor(cli.connect, plugins, "fixture:links", {"link": "a>b"})
    check("a relation names the extractor that stated it", ("a>b", "linksTo", "fixture:notes") in rel()
          and ("a>b", "mentions", "fixture:links") in rel(), rel())
    run_extractor(cli.connect, plugins, "fixture:notes", {"text": "a: one\nb: two", "link": "a>b"})
    check("a run replaces its own relations and leaves another author's", rel() == {
        ("a>b", "linksTo", "fixture:notes"), ("a>b", "mentions", "fixture:links")}, rel())
    run_extractor(cli.connect, plugins, "fixture:notes", {"text": "b: two", "link": ""})
    check("an item gone from the source loses its extractor's relations, not another's",
          rel() == {("a>b", "mentions", "fixture:links")}, rel())

    now = time.time()
    good = token({"role": "wb_viewer", "name": "vi", "exp": int(now) + 60})
    check("the server accepts a token PostgREST would", verify(good, os.environ["WORKBENCH_JWT_SECRET"]) is not None)
    check("an expired token is refused", verify(token({"role": "wb_viewer", "exp": int(now) - 1}), os.environ["WORKBENCH_JWT_SECRET"]) is None)
    check("a token signed with another secret is refused", verify(token({"role": "wb_owner", "exp": int(now) + 60}, "x" * 40), os.environ["WORKBENCH_JWT_SECRET"]) is None)
    check("a token for another role is refused", verify(token({"role": "postgres", "exp": int(now) + 60}), os.environ["WORKBENCH_JWT_SECRET"]) is None)
    check("a malformed token is refused", verify("not.a.token", os.environ["WORKBENCH_JWT_SECRET"]) is None)
    with cli.connect() as conn:
        conn.execute("set role wb_editor")
        try:
            conn.execute("select wb.retract_missing('x', 'note', '{}'::uuid[])")
            check("only the server may retract", False, "an editor could")
        except psycopg.errors.InsufficientPrivilege:
            check("only the server may retract", True)
finally:
    with psycopg.connect(cli.url("postgres"), autocommit=True) as conn:
        conn.execute(sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(DB)))

print(f"{sum(checks)}/{len(checks)} checks passed")
sys.exit(0 if all(checks) else 1)
