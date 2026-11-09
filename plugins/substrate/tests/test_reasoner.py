"""substrate:reasoner and the graph views on substrate's own vocabulary, in a throwaway database: a chain of observed
relations (route proxiesTo container, container dialsTo container, container mounts volume) makes the route reach the
volume by prp-spo1 and prp-trp, as a claim of the reasoner quoting its premises; taking a premise away retracts the
conclusion at once; the generated mapping types each item by its term; pgGraph's path follows the relations.

    WORKBENCH_ADMIN_URL=postgresql://postgres:...@127.0.0.1:5432/postgres python3 plugins/substrate/tests/test_reasoner.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "workbench")]
os.environ["WORKBENCH_DB"] = DB = f"workbench_test_{os.getpid()}"
os.environ.setdefault("WORKBENCH_JWT_SECRET", "r-" + "z" * 40)

import psycopg  # noqa: E402
from psycopg import sql  # noqa: E402

from workbench import cli, graph  # noqa: E402
from workbench.extract import Plugins, run_extractor  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print(("ok  " if ok else "FAIL"), name, "" if ok else detail)


def chain(ctx, inputs):
    """A stand-in observer: four items and the relations inputs['links'] names (a>b:predicate, comma-separated)."""
    ids = {"r": ctx.upsert("route", "r", {"match": []}, title="/api/*"), "p": ctx.upsert("container", "p", {}, title="api"),
           "d": ctx.upsert("container", "d", {}, title="db"), "v": ctx.upsert("volume", "v", {}, title="data")}
    kinds = {"r": "route", "p": "container", "d": "container", "v": "volume"}
    for link in inputs["links"].split(","):
        ab, pred = link.split(":")
        a, b = ab.split(">")
        ctx.relate(kinds[a], ids[a], pred, kinds[b], ids[b], quote=link)
    for t in ("route", "container", "volume"):
        ctx.done(t)


def reach(conn):
    return conn.execute("""select c.status, c.quote, jsonb_array_length(c.span -> 'premises'), c.span ->> 'rule'
                             from wb.claim c join content.route r on r.id = c.subject_id join content.volume v on v.id = c.object_id
                            where c.author = 'substrate:reasoner' and c.field = 'reaches' order by c.observed_at desc""").fetchall()


try:
    cli.migrate()
    cli.load_plugin(ROOT / "plugins/substrate")
    plugins = Plugins().load(ROOT / "plugins")
    plugins.extractors["test:chain"] = {"key": "test:chain", "plugin": "substrate", "name": "chain", "fn": chain, "description": "", "inputs": {}}
    full = "r>p:proxiesTo,p>d:dialsTo,d>v:mounts"
    run_extractor(cli.connect, plugins, "test:chain", {"links": full})
    r = run_extractor(cli.connect, plugins, "substrate:reasoner", {})
    with cli.connect() as conn:
        got = reach(conn)
        check("the reasoner runs", r.get("ok"), r)
        check("a route reaches the volume its data lives on (prp-spo1, prp-trp)", got and got[0][0] == "current" and got[0][3] == "prp-trp", got)
        check("the conclusion quotes the chain and rests on its three stated claims",
              got and "proxiesTo" in got[0][1] and "mounts" in got[0][1] and got[0][2] == 3, got)
        stated = conn.execute("select count(*) from wb.relation where author = 'substrate:reasoner' and predicate = 'proxiesTo'").fetchone()[0]
        check("nothing a query-time reasoner can do is written back (no copies of sub-properties)", stated == 0)
    again = run_extractor(cli.connect, plugins, "substrate:reasoner", {})
    with cli.connect() as conn:
        check("reasoning again adds nothing", len([x for x in reach(conn) if x[0] == "current"]) == 1, reach(conn))
    run_extractor(cli.connect, plugins, "test:chain", {"links": "r>p:proxiesTo,p>d:dialsTo"})
    with cli.connect() as conn:
        check("a premise taken away retracts the conclusion at once, before the reasoner runs again",
              all(x[0] == "retracted" for x in reach(conn)) and reach(conn), reach(conn))
        check("and its relation row goes with it", conn.execute(
            "select count(*) from wb.relation r join content.volume v on v.id = r.to_id where r.predicate = 'reaches'").fetchone()[0] == 0)

    run_extractor(cli.connect, plugins, "test:chain", {"links": full})
    run_extractor(cli.connect, plugins, "substrate:reasoner", {})
    with cli.connect() as conn:
        obda, ttl = graph.mapping(conn), graph.ontology(conn)
        check("the mapping types each item by its term", "a <https://substrate.local/ns#Route>" in obda and "a <https://substrate.local/ns#Volume>" in obda)
        check("a field named like a keyword is quoted", 'SELECT id, "where" AS v FROM content.setting' in obda)
        check("the ontology carries the vocabulary's axioms", "<https://substrate.local/ns#reaches> a owl:ObjectProperty, owl:TransitiveProperty" in ttl
              and "rdfs:subPropertyOf <https://substrate.local/ns#reaches>" in ttl)
        p = graph.project(conn)
        check("pgGraph's projection builds over every content type", p.get("node_tables", 0) >= 17, p)
        path = conn.execute("select type, slug, predicate from api.graph_path('route', 'r', 'volume', 'v')").fetchall()
        preds = [x[2] for x in path if x[2]]
        check("a path from the route reaches the volume, along the relations' direction",
              path and path[-1][1] == "v" and ("reaches" in preds or preds[:3] == ["proxiesTo", "dialsTo", "mounts"]), path)
        back = conn.execute("select count(*) from api.graph_path('volume', 'v', 'route', 'r')").fetchone()[0]
        check("and not against it", back == 0, back)
    with cli.connect() as conn:                   # a new session, as an ordinary reader: pgGraph applies its rights
        conn.execute("set role wb_viewer")
        mine = conn.execute("select slug from api.graph_path('route', 'r', 'volume', 'v')").fetchall()
        check("a reader gets the same path as themselves (schema usage, table SELECT, graph read; nothing internal)",
              mine and mine[-1][0] == "v", mine)
finally:
    with psycopg.connect(cli.url("postgres"), autocommit=True) as conn:
        conn.execute(sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(DB)))

print(f"{sum(checks)}/{len(checks)} checks passed")
sys.exit(0 if all(checks) else 1)
