"""W1 checks (BRIEF.md section 9): the store, the rules and sign-in, in a throwaway database.

    WORKBENCH_ADMIN_URL=postgresql://postgres:...@127.0.0.1:5432/postgres python3 tests/test_w1.py

Requests are played as PostgREST makes them: switch to the token's role and set request.jwt.claims for the
transaction. The database is dropped at the end; the server-wide wb_* roles stay.
"""
import base64
import hashlib
import hmac
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
DB = f"workbench_test_{os.getpid()}"
os.environ["WORKBENCH_DB"] = DB
os.environ.setdefault("WORKBENCH_JWT_SECRET", "test-secret-" + "x" * 32)

import psycopg  # noqa: E402
from psycopg import sql  # noqa: E402

from workbench import cli  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print(("ok  " if ok else "FAIL"), name, "" if ok else detail)


def as_user(conn, role, name, statement, args=()):
    """One request, as PostgREST runs it: the role and claims for this transaction only."""
    with conn.transaction():
        conn.execute(sql.SQL("set local role {}").format(sql.Identifier(role)))
        conn.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({"role": role, "name": name}),))
        return conn.execute(statement, args).fetchall()


def unb64(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


try:
    out = cli.migrate()
    check("migrate creates the database and applies the core", out["created"] and out["applied"] == sorted(f.name for f in (HERE.parent / "workbench/sql").glob("*.sql")))
    check("migrate again applies nothing", cli.migrate()["applied"] == [])
    loaded = cli.load_plugin(HERE / "fixtures/plugin")
    check("a plugin's content type gets its table", loaded["types"][0]["type"] == "note"
          and set(loaded["types"][0]["added"]) == {"body", "stars", "tags", "due"})
    ed = cli.user("add", "ed", "editor")["password"]
    cli.user("add", "vi", "viewer")
    with cli.connect() as conn:
        conn.autocommit = True
        cols = dict(conn.execute("select column_name, data_type from information_schema.columns"
                                 " where table_schema = 'content' and table_name = 'note'").fetchall())
        check("properties become typed columns", cols.get("stars") == "bigint" and cols.get("tags") == "jsonb"
              and cols.get("due") == "timestamp with time zone" and cols.get("body") == "text", cols)

        # an editor writes through the API view; every set field becomes a claim attributed to them
        nid = as_user(conn, "wb_editor", "ed", "insert into api.note (title, body, stars) values ('First', 'hello', 3)"
                      " returning id")[0][0]
        claims = as_user(conn, "wb_viewer", "vi", "select field, value, author, status from api.claims"
                         " where subject_id = %s order by field", (nid,))
        check("a write records one claim per field set, by its author",
              [(f, a, s) for f, _, a, s in claims] == [("body", "ed", "current"), ("stars", "ed", "current"),
                                                       ("title", "ed", "current")], claims)
        row = as_user(conn, "wb_viewer", "vi", "select created_by, updated_by from api.note where id = %s", (nid,))[0]
        check("the item says who made it", row == ("ed", "ed"), row)

        # a change supersedes the same author's earlier claim; an unchanged field claims nothing new
        as_user(conn, "wb_editor", "ed", "update api.note set stars = 4, body = 'hello' where id = %s returning id", (nid,))
        stars = as_user(conn, "wb_viewer", "vi", "select value, status from api.claims where subject_id = %s"
                        " and field = 'stars' order by observed_at", (nid,))
        check("an edit supersedes the earlier claim", [(v, s) for v, s in stars] == [(3, "superseded"), (4, "current")], stars)
        body = as_user(conn, "wb_viewer", "vi", "select count(*) from api.claims where subject_id = %s and field = 'body'", (nid,))
        check("an unchanged field adds no claim", body[0][0] == 1, body)
        # back to an earlier value: a new current claim, not a lost one
        as_user(conn, "wb_editor", "ed", "update api.note set stars = 3 where id = %s returning id", (nid,))
        cur = as_user(conn, "wb_viewer", "vi", "select value from api.claims where subject_id = %s and field = 'stars'"
                      " and status = 'current'", (nid,))
        check("returning to an earlier value is current again", cur == [(3,)], cur)

        # another source's claim about the same field stays beside it
        as_user(conn, "wb_editor", "other", "update api.note set stars = 5 where id = %s returning id", (nid,))
        both = as_user(conn, "wb_viewer", "vi", "select author, value from api.claims where subject_id = %s"
                       " and field = 'stars' and status = 'current' order by author", (nid,))
        check("a different author's claim does not supersede ed's", both == [("ed", 3), ("other", 5)], both)

        for what, stmt in (("insert", "insert into api.note (title) values ('nope') returning id"),
                           ("update", f"update api.note set title = 'nope' where id = '{nid}' returning id")):
            try:
                as_user(conn, "wb_viewer", "vi", stmt)
                check(f"a viewer cannot {what}", False, "it could")
            except psycopg.errors.InsufficientPrivilege:
                check(f"a viewer cannot {what}", True)
        for who, role in (("ed", "wb_editor"), ("vi", "wb_viewer")):
            try:
                as_user(conn, role, who, f"delete from api.note where id = '{nid}' returning id")
                check(f"{who} cannot delete", False, "deleted")
            except psycopg.errors.InsufficientPrivilege:
                check(f"{who} cannot delete", True)
        try:
            as_user(conn, "wb_editor", "ed", "insert into wb.claim (subject_type, subject_id, field, hash)"
                    " values ('note', gen_random_uuid(), 'x', 'x') returning id")
            check("nobody writes claims directly", False, "inserted")
        except psycopg.errors.InsufficientPrivilege:
            check("nobody writes claims directly", True)
        try:
            as_user(conn, "wb_anon", "", "select * from api.note")
            check("an anonymous request reads nothing", False, "it read")
        except psycopg.errors.InsufficientPrivilege:
            check("an anonymous request reads nothing", True)

        # the review lane: a decision waits; viewers see it, an editor decides it once, with their name
        did = conn.execute("insert into wb.decision (kind, subject) values ('gap', '{\"text\": \"x\"}') returning id").fetchone()[0]
        seen = as_user(conn, "wb_viewer", "vi", "select status from api.decisions where id = %s", (did,))
        check("a viewer sees an open decision", seen == [("open",)], seen)
        try:
            as_user(conn, "wb_viewer", "vi", "select api.decide(%s, true, null)", (did,))
            check("a viewer cannot decide", False, "decided")
        except psycopg.errors.InsufficientPrivilege:
            check("a viewer cannot decide", True)
        res = as_user(conn, "wb_editor", "ed", "select api.decide(%s, true, 'looks right')", (did,))[0][0]
        check("an editor decides, and the decision carries their name", res["status"] == "approved" and res["decided_by"] == "ed", res)
        try:
            as_user(conn, "wb_editor", "ed", "select api.decide(%s, false, null)", (did,))
            check("a decision is made once", False, "decided twice")
        except psycopg.errors.NoDataFound:
            check("a decision is made once", True)

        # sign-in: anonymous may call login; the token is a JWT PostgREST can verify with the shared secret
        tok = as_user(conn, "wb_anon", "", "select api.login('ed', %s)", (ed,))[0][0]
        h, p, s = tok["token"].split(".")
        good = hmac.compare_digest(unb64(s), hmac.new(os.environ["WORKBENCH_JWT_SECRET"].encode(),
                                                      f"{h}.{p}".encode(), hashlib.sha256).digest())
        payload = json.loads(unb64(p))
        check("login returns an HS256 JWT with the person's role and name",
              good and json.loads(unb64(h))["alg"] == "HS256" and payload["role"] == "wb_editor"
              and payload["name"] == "ed" and payload["exp"] > 0, payload)
        try:
            as_user(conn, "wb_anon", "", "select api.login('ed', 'wrong')")
            check("a wrong password is refused", False, "accepted")
        except psycopg.errors.InvalidPassword:
            check("a wrong password is refused", True)
        try:
            as_user(conn, "wb_anon", "", "select * from wb_private.person")
            check("nobody reads the password table", False, "read")
        except psycopg.errors.InsufficientPrivilege:
            check("nobody reads the password table", True)
    with cli.connect() as conn:                      # retiring: nothing deleted, every claim behind it retracted
        conn.autocommit = True
        nid = as_user(conn, "wb_editor", "ed", "insert into api.note (slug, title, body, stars) values ('gone', 'Gone', 'x', 2) returning id")[0][0]
        live = lambda: conn.execute("select wb.live(%s)", (nid,)).fetchone()[0]  # noqa: E731
        try:
            as_user(conn, "wb_viewer", "vi", "select api.retire('note', %s, 'no')", (nid,))
            check("a viewer may not retire", False, "allowed")
        except psycopg.errors.InsufficientPrivilege:
            check("a viewer may not retire", True)
        r = as_user(conn, "wb_editor", "ed", "select api.retire('note', %s, 'duplicate of another')", (nid,))[0][0]
        rows = conn.execute("select field, status, author, value from wb.claim where subject_id = %s order by field", (nid,)).fetchall()
        check("retiring retracts every claim and records who and why, the row stays",
              r["retracted"] >= 3 and not live() and ("_retired", "current", "ed", "duplicate of another") in rows
              and all(st == "retracted" for f, st, _, _ in rows if f != "_retired")
              and conn.execute("select count(*) from content.note where id = %s", (nid,)).fetchone()[0] == 1, (r, rows))
        as_user(conn, "wb_editor", "ed", "update api.note set stars = 5 where id = %s returning id", (nid,))
        r = as_user(conn, "wb_editor", "ed", "select api.restore('note', %s)", (nid,))[0][0]
        cur = dict(conn.execute("select field, value from wb.claim where subject_id = %s and status = 'current'", (nid,)).fetchall())
        check("restoring brings the claims back, except a field written since", live() and cur.get("stars") == 5
              and cur.get("body") == "x" and "_retired" not in cur, (r, cur))
    new = cli.user("reset", "ed", "editor")["password"]
    with cli.connect() as conn:
        conn.autocommit = True
        ok = as_user(conn, "wb_anon", "", "select api.login('ed', %s)", (new,))[0][0]["role"] == "wb_editor"
        check("a reset password signs in", ok)
    check("user list shows roles, not passwords", cli.user("list", None, "") == [
        {"name": "ed", "role": "editor", "disabled": False}, {"name": "vi", "role": "viewer", "disabled": False}])
finally:
    with psycopg.connect(cli.url("postgres"), autocommit=True) as conn:
        conn.execute(sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(DB)))

print(f"{sum(checks)}/{len(checks)} checks passed")
sys.exit(0 if all(checks) else 1)
