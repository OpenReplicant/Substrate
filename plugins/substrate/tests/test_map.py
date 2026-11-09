"""The map held in Workbench (MAP.md), in a throwaway database: a catalog file imports and exports back to the same
entities, in the same bytes each time; an edit made in Workbench shows in the export and makes a plain import refuse;
retiring an entry takes it out of the export and its relations out of the graph, and restoring brings both back.

    WORKBENCH_ADMIN_URL=postgresql://postgres:...@127.0.0.1:5432/postgres python3 plugins/substrate/tests/test_map.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "workbench"), str(ROOT / "plugins/substrate")]
os.environ["WORKBENCH_DB"] = DB = f"workbench_test_{os.getpid()}"
os.environ.setdefault("WORKBENCH_JWT_SECRET", "m-" + "z" * 40)

import psycopg  # noqa: E402
from psycopg import sql  # noqa: E402

import substrate_map as sm  # noqa: E402
from workbench import cli  # noqa: E402
from workbench.extract import Plugins, run_extractor  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print(("ok  " if ok else "FAIL"), name, "" if ok else detail)


CATALOG = """# a hand-written file: comments and flow style do not survive, the entities do
apiVersion: backstage.io/v1alpha1
kind: Domain
metadata: {name: shop, description: A small shop}
spec: {owner: group:ops}
---
apiVersion: backstage.io/v1alpha1
kind: Group
metadata: {name: ops, description: The people who run it}
spec: {type: team, children: []}
---
apiVersion: backstage.io/v1alpha1
kind: System
metadata: {name: web, description: What customers see}
spec: {owner: group:ops, domain: shop}
---
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: storefront
  title: The storefront
  description: Pages and checkout
  annotations: {substrate.dev/intent: sell things, substrate.dev/observed-as: "container:shop-web-*"}
spec: {type: service, lifecycle: production, owner: group:ops, system: web, dependsOn: [resource:orders-db], providesApis: [shop-api]}
---
apiVersion: backstage.io/v1alpha1
kind: Resource
metadata: {name: orders-db, description: Orders}
spec: {type: database, owner: group:ops, system: web}
---
apiVersion: backstage.io/v1alpha1
kind: API
metadata: {name: shop-api, description: The shop's HTTP API}
spec: {type: openapi, lifecycle: production, owner: group:ops, system: web, definition: "GET /products"}
"""


def export(conn):
    return sm.dump(sm.entities(conn, "shop"), "shop")


def as_editor(conn, name, statement, args=()):
    with conn.transaction():
        conn.execute("set local role wb_editor")
        conn.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({"role": "wb_editor", "name": name}),))
        return conn.execute(statement, args).fetchall()


def relations(conn):
    return sorted(conn.execute("""select f.slug, r.predicate, t.slug from wb.relation r join content.component f on f.id = r.from_id
                                  join content.component t on t.id = r.to_id""").fetchall())


try:
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "catalog-info.yaml").write_text(CATALOG)
        os.environ["WB_SUBSTRATE_ROOT"] = d
        cli.migrate()
        cli.load_plugin(ROOT / "plugins/substrate")
        plugins = Plugins().load(ROOT / "plugins")
        r = run_extractor(cli.connect, plugins, "substrate:catalog", {})
        run_extractor(cli.connect, plugins, "substrate:map", {})
        with cli.connect() as conn:
            conn.autocommit = True
            first = export(conn)
            check("a file imports, and exports back to the same entities", r.get("ok") and
                  sm.normalized(yaml.safe_load_all(CATALOG)) == sm.normalized(yaml.safe_load_all(first)), (r, first))
            check("exporting an unchanged map gives the same bytes", export(conn) == first)
            rel = relations(conn)
            check("the map's relations come from its fields", {("storefront", "dependsOn", "orders-db"),
                  ("storefront", "providesApi", "api-shop-api"), ("storefront", "partOf", "system-web"),
                  ("system-web", "partOf", "domain-shop")} <= set(rel), rel)

            as_editor(conn, "pat", "update api.component set description = 'Pages, search and checkout' where slug = 'storefront' returning id")
            check("an edit in Workbench shows in the export", "Pages, search and checkout" in export(conn))
        r = run_extractor(cli.connect, plugins, "substrate:catalog", {})
        check("importing over an edit is refused", not r.get("ok") and "changed in Workbench" in str(r.get("error")), r)
        with cli.connect() as conn:
            conn.autocommit = True
            check("and the edit stands", "Pages, search and checkout" in export(conn))
            db = conn.execute("select id from api.component where slug = 'orders-db'").fetchone()[0]
            as_editor(conn, "pat", "select api.retire('component', %s, 'moved to the shared database')", (db,))
            gone = export(conn)
        run_extractor(cli.connect, plugins, "substrate:map", {})
        with cli.connect() as conn:
            conn.autocommit = True
            check("a retired entry leaves the export", "name: orders-db" not in gone and "name: storefront" in gone, gone)
            check("and its relations leave the graph", not any("orders-db" in (a, b) for a, _, b in relations(conn)), relations(conn))
            as_editor(conn, "pat", "select api.restore('component', %s)", (db,))
        run_extractor(cli.connect, plugins, "substrate:map", {})
        with cli.connect() as conn:
            check("restoring brings it back, relations too", "name: orders-db" in export(conn)
                  and ("storefront", "dependsOn", "orders-db") in relations(conn))
finally:
    with psycopg.connect(cli.url("postgres"), autocommit=True) as conn:
        conn.execute(sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(DB)))

print(f"{sum(checks)}/{len(checks)} checks passed")
sys.exit(0 if all(checks) else 1)
