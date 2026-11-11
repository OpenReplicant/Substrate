"""Recall (BRIEF.md section 6, sql/013_recall.sql, workbench/embed.py) in a throwaway database, with a fake
embeddings endpoint whose vectors put synonyms together, so meaning can find what words cannot.

    WORKBENCH_ADMIN_URL=postgresql://postgres:...@127.0.0.1:5432/postgres python3 tests/test_recall.py
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
DB = f"workbench_test_{os.getpid()}"
os.environ["WORKBENCH_DB"] = DB
os.environ.setdefault("WORKBENCH_JWT_SECRET", "test-secret-" + "r" * 32)

import psycopg  # noqa: E402
from psycopg import sql  # noqa: E402

from workbench import cli, embed  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print(("ok  " if ok else "FAIL"), name, "" if ok else detail)


# each concept is one dimension; synonyms share it
CONCEPTS = [("car", "automobile", "vehicle"), ("rain", "weather", "storm"), ("invoice", "bill", "payment"),
            ("garden", "plants"), ("queue", "jobs")]
CALLS = {"n": 0}


def vec(text):
    words = set(text.lower().replace(":", " ").split())
    v = [1.0 if words & set(c) else 0.0 for c in CONCEPTS] + [0.05]
    n = sum(x * x for x in v) ** 0.5
    return [x / n for x in v]


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        CALLS["n"] += len(body["input"])
        out = json.dumps({"data": [{"index": i, "embedding": vec(t)} for i, t in enumerate(body["input"])]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


def as_user(conn, role, name, statement, args=()):
    with conn.transaction():
        conn.execute(sql.SQL("set local role {}").format(sql.Identifier(role)))
        conn.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({"role": role, "name": name}),))
        return conn.execute(statement, args).fetchall()


server = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=server.serve_forever, daemon=True).start()
os.environ.update({"WORKBENCH_EMBED_URL": f"http://127.0.0.1:{server.server_port}", "WORKBENCH_EMBED_MODEL": "fake-1"})
try:
    cli.migrate()
    cli.load_plugin(HERE / "fixtures/plugin")
    cli.user("add", "ed", "editor")
    cli.user("add", "vi", "viewer")
    with cli.connect() as conn:
        conn.autocommit = True
        ids = {}
        for title, body in (("Car service", "the car needs new tyres"), ("Rain gear", "pack for the storm"),
                            ("Invoice 12", "send the invoice by Friday"), ("Garden", "water the plants"),
                            ("Work queue", "jobs wait on the queue")):
            ids[title] = as_user(conn, "wb_editor", "ed", "insert into api.note (title, body) values (%s, %s) returning id",
                                 (title, body))[0][0]
        conn.execute("insert into wb.relation (from_type, from_id, predicate, to_type, to_id) values ('note', %s, 'relatedTo', 'note', %s)",
                     (ids["Car service"], ids["Invoice 12"]))
        cfg = embed.settings()
        r = embed.embed(conn, cfg)
        check("embed makes a vector for every live item", r["embedded"] == 5 and r["items"] == 5, r)
        r = embed.embed(conn, cfg)
        check("and makes none again when nothing changed", r["embedded"] == 0, r)
        as_user(conn, "wb_editor", "ed", "update api.note set body = 'the automobile needs new tyres' where id = %s returning id",
                (ids["Car service"],))
        r = embed.embed(conn, cfg)
        check("a changed item is embedded again, and only it", r["embedded"] == 1, r)

        def titles(q, **kw):
            return [(h["title"], h["via"]) for h in embed.recall(conn, q, **kw)]

        words = titles("vehicle", use_vectors=False, depth=0)
        meaning = titles("vehicle", depth=0)
        check("words alone cannot find a synonym", not words, words)
        check("meaning can", meaning and meaning[0] == ("Car service", "vector"), meaning)
        both = titles("storm", depth=0)
        check("an item found both ways says so", both and both[0][0] == "Rain gear" and set(both[0][1].split("+")) == {"text", "vector"}, both)
        near = titles("vehicle", depth=1)
        check("the graph brings what the best hit is related to", ("Invoice 12", "vector+graph") in near or
              any(t == "Invoice 12" and "graph" in v for t, v in near), near)
        check("and not without it", not any("graph" in v for _, v in titles("vehicle", depth=0)), titles("vehicle", depth=0))
        qv = embed.query_vector(cfg, "payment")
        rows = as_user(conn, "wb_viewer", "vi", "select title, via from api.recall('payment', %s::vector, 'fake-1', 5, 0)", (qv,))
        check("a viewer recalls through the API as themselves", rows and rows[0][0] == "Invoice 12", rows)
        conn.execute("select set_config('request.jwt.claims', %s, false)", (json.dumps({"role": "wb_owner", "name": "ed"}),))
        conn.execute("select api.retire('note', %s, 'done')", (ids["Garden"],))
        gone = titles("plants", depth=0)
        check("a retired item is not recalled", not any(t == "Garden" for t, _ in gone), gone)
        r = embed.embed(conn, cfg)
        check("and its vector is dropped", r["dropped"] == 1, r)
        other = conn.execute("select count(*) from api.recall('vehicle', %s::vector, 'another-model', 5, 0) where via like '%%vector%%'",
                             (embed.query_vector(cfg, "vehicle"),)).fetchone()[0]
        check("vectors are only compared within their own model", other == 0, other)
finally:
    server.shutdown()
    with psycopg.connect(cli.url("postgres"), autocommit=True) as conn:
        conn.execute(sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(DB)))

print(f"{sum(checks)}/{len(checks)} checks passed")
sys.exit(0 if all(checks) else 1)
