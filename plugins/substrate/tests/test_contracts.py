"""substrate:contracts in a throwaway database: a contract run's result file becomes a contract item whose values quote
the file, related to the API it tests and to the part whose substrate.dev/filler names the filler; a failing run
says which checks failed; a run whose file is gone is retracted.

    WORKBENCH_ADMIN_URL=postgresql://postgres:...@127.0.0.1:5432/postgres python3 plugins/substrate/tests/test_contracts.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "workbench")]
os.environ["WORKBENCH_DB"] = DB = f"workbench_test_{os.getpid()}"
os.environ.setdefault("WORKBENCH_JWT_SECRET", "c-" + "z" * 40)

import psycopg  # noqa: E402
from psycopg import sql  # noqa: E402

from workbench import cli  # noqa: E402
from workbench.extract import Plugins, run_extractor  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print(("ok  " if ok else "FAIL"), name, "" if ok else detail)


CATALOG = """apiVersion: backstage.io/v1alpha1
kind: API
metadata: {name: store-api, description: a slot}
spec: {type: contract, owner: group:x, system: core}
---
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: plain-store
  annotations: {substrate.dev/filler: plain}
spec: {type: library, owner: group:x, system: core, providesApis: [store-api]}
---
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: other-store
  annotations: {substrate.dev/filler: other}
spec: {type: library, owner: group:x, system: core, lifecycle: option, providesApis: [store-api]}
"""


def result(folder: Path, filler: str, ok: bool):
    (folder / f"store-api--{filler}.json").write_text(json.dumps({
        "interface": "store-api", "filler": filler, "passed": ok, "host": "h", "ran_at": "2026-11-09T00:00:00+00:00",
        "command": f"scripts/contract.sh store-api {filler}",
        "checks": [{"name": "it answers", "ok": True, "detail": ""}, {"name": "it keeps a value", "ok": ok, "detail": "" if ok else "lost"}]}))


try:
    with tempfile.TemporaryDirectory() as d:
        repo = Path(d)
        (repo / "catalog-info.yaml").write_text(CATALOG)
        (repo / ".state/contracts").mkdir(parents=True)
        result(repo / ".state/contracts", "plain", True)
        result(repo / ".state/contracts", "other", False)
        os.environ["WB_SUBSTRATE_ROOT"] = str(repo)
        cli.migrate()
        cli.load_plugin(ROOT / "plugins/substrate")
        plugins = Plugins().load(ROOT / "plugins")
        run_extractor(cli.connect, plugins, "substrate:catalog", {})
        r = run_extractor(cli.connect, plugins, "substrate:contracts", {})
        with cli.connect() as conn:
            rows = dict(((s, (p, f)) for s, p, f in conn.execute("select slug, passed, failed from content.contract").fetchall()))
            rel = {(f, p, t) for f, p, t in conn.execute(
                """select c.slug, r.predicate, t.slug from wb.relation r join content.contract c on c.id = r.from_id
                   join content.component t on t.id = r.to_id""").fetchall()}
            quote = conn.execute("""select cl.quote, s.uri from wb.claim cl join content.contract c on c.id = cl.subject_id
                                    join wb.source s on s.id = cl.source_id where c.slug = 'store-api-other' and cl.field = 'passed'""").fetchone()
        check("each run becomes a contract item, pass or fail", r.get("ok") and rows.get("store-api-plain", (None,))[0] is True
              and rows.get("store-api-other", (None,))[0] is False, (r, rows))
        check("a failing run names the checks that failed", rows.get("store-api-other", (None, None))[1] == ["it keeps a value"], rows)
        check("its values quote the result file", quote and quote[0] == 'false' and quote[1].endswith("store-api--other.json"), quote)
        check("a run tests its API and ran against the part its filler names",
              {("store-api-plain", "tests", "api-store-api"), ("store-api-plain", "ranAgainst", "plain-store"),
               ("store-api-other", "ranAgainst", "other-store")} <= rel, rel)
        (repo / ".state/contracts/store-api--other.json").unlink()
        run_extractor(cli.connect, plugins, "substrate:contracts", {})
        with cli.connect() as conn:
            gone = conn.execute("""select count(*) from wb.claim cl join content.contract c on c.id = cl.subject_id
                                   where c.slug = 'store-api-other' and cl.status = 'current'""").fetchone()[0]
        check("a run whose file is gone is retracted", gone == 0, gone)
finally:
    with psycopg.connect(cli.url("postgres"), autocommit=True) as conn:
        conn.execute(sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(DB)))

print(f"{sum(checks)}/{len(checks)} checks passed")
sys.exit(0 if all(checks) else 1)
