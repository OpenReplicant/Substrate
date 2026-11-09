"""substrate:drift in a throwaway database: a part whose substrate.dev/observed-as names a running container is related
to it (observedAs); when the last thing it ran as is gone, that relation goes too and the part's gap is raised; a
container no part claims is a gap of its own.

    WORKBENCH_ADMIN_URL=postgresql://postgres:...@127.0.0.1:5432/postgres python3 plugins/substrate/tests/test_drift.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "workbench")]
os.environ["WORKBENCH_DB"] = DB = f"workbench_test_{os.getpid()}"
os.environ.setdefault("WORKBENCH_JWT_SECRET", "d-" + "z" * 40)

import psycopg  # noqa: E402
from psycopg import sql  # noqa: E402

from workbench import cli  # noqa: E402
from workbench.extract import Plugins, run_extractor  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print(("ok  " if ok else "FAIL"), name, "" if ok else detail)


CATALOG = """apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: shop-web
  annotations: {substrate.dev/observed-as: "container:shop-web-*"}
spec: {type: service, owner: group:x, system: core}
"""


def running(ctx, inputs):
    """A stand-in for the observer: the containers inputs['names'] lists (comma-separated), nothing else."""
    for name in filter(None, inputs.get("names", "").split(",")):
        ctx.upsert("container", name, {"state": "running"}, title=name)
    ctx.done("container")


def state(conn):
    rel = conn.execute("""select t.slug from wb.relation r join content.component c on c.id = r.from_id
                          join content.container t on t.id = r.to_id where r.predicate = 'observedAs'""").fetchall()
    gaps = conn.execute("select key from wb.decision where raised_by = 'substrate:drift' and status = 'open'").fetchall()
    return sorted(x[0] for x in rel), sorted(x[0] for x in gaps)


try:
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "catalog-info.yaml").write_text(CATALOG)
        os.environ["WB_SUBSTRATE_ROOT"] = d
        cli.migrate()
        cli.load_plugin(ROOT / "plugins/substrate")
        plugins = Plugins().load(ROOT / "plugins")
        plugins.extractors["substrate:observed"] = {"key": "substrate:observed", "plugin": "substrate", "name": "observed",
                                                    "fn": running, "description": "", "inputs": {}}
        run_extractor(cli.connect, plugins, "substrate:catalog", {})

        run_extractor(cli.connect, plugins, "substrate:observed", {"names": "shop-web-1,stray"})
        r = run_extractor(cli.connect, plugins, "substrate:drift", {})
        with cli.connect() as conn:
            rel, gaps = state(conn)
        check("drift runs", r.get("ok"), r)
        check("a part is related to the container its observed-as names", rel == ["shop-web-1"], rel)
        check("a container no part claims is a gap", gaps == ["undeclared:container:stray"], gaps)

        run_extractor(cli.connect, plugins, "substrate:observed", {"names": "stray"})
        run_extractor(cli.connect, plugins, "substrate:drift", {})
        with cli.connect() as conn:
            rel, gaps = state(conn)
        check("when the last thing a part ran as is gone, its observedAs goes too", rel == [], rel)
        check("and the part's gap is raised", "unobserved:container:shop-web-*" in gaps, gaps)
finally:
    with psycopg.connect(cli.url("postgres"), autocommit=True) as conn:
        conn.execute(sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(DB)))

print(f"{sum(checks)}/{len(checks)} checks passed")
sys.exit(0 if all(checks) else 1)
