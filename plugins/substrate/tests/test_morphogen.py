"""substrate:morphogen against Morphogen's own writer: verdicts become items with their evidence, a probe is not a
verdict, reading again adds nothing, and a tampered log is refused with nothing kept. In a throwaway database.

    WORKBENCH_ADMIN_URL=postgresql://postgres:...@127.0.0.1:5432/postgres python3 plugins/substrate/tests/test_morphogen.py
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "workbench")]
os.environ["WORKBENCH_DB"] = DB = f"workbench_test_{os.getpid()}"
os.environ.setdefault("WORKBENCH_JWT_SECRET", "m-" + "z" * 40)

import psycopg  # noqa: E402
from psycopg import sql  # noqa: E402

import importlib.util  # noqa: E402

# Morphogen's own writer, its one file loaded directly: the package's __init__ needs Morphogen's whole environment
_spec = importlib.util.spec_from_file_location("morphogen_evidence", ROOT / "repos/morphogen/morphogen/evidence.py")
_evidence = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_evidence)
Evidence = _evidence.Evidence
from workbench import cli  # noqa: E402
from workbench.extract import Plugins, run_extractor  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print(("ok  " if ok else "FAIL"), name, "" if ok else detail)


def verdict(cell, base, cand, passed):
    return {"claim": f"{cell}: {cand[:12]} is {'better than' if passed else 'not better than'} {base[:12]}", "kind": "verdict",
            "verdict": "pass" if passed else "fail", "subject": {"system": cell, "path": "."}, "cell": cell,
            "outcome": {"check": True, "metrics": {"wall_seconds": {"gain": 0.12, "sign_test_p": 0.01, "ok": passed}}},
            "refs": {"base": base, "candidate": cand}, "gate": {"decision": "review"}, "trust": "measured", "by": "judge"}


with tempfile.TemporaryDirectory() as d:
    log = Path(d) / "evidence.db"
    ev = Evidence(log)
    ev.append(verdict("setup", "a" * 40, "b" * 40, True))
    ev.append({"claim": "probe", "kind": "probe", "subject": {"system": "setup"}, "trust": "measured", "by": "judge"})
    ev.append(verdict("map", "c" * 40, "d" * 40, False))
    try:
        cli.migrate()
        cli.load_plugin(ROOT / "plugins/substrate")
        plugins = Plugins().load(ROOT / "plugins")
        r = run_extractor(cli.connect, plugins, "substrate:morphogen", {"log": str(log)})
        with cli.connect() as conn:
            rows = conn.execute("select slug, verdict, gate, cell, trust, seq, metrics from content.verdict order by seq").fetchall()
            q = conn.execute("select c.quote, c.span, s.uri from wb.claim c join content.verdict v on v.id = c.subject_id"
                             " join wb.source s on s.id = c.source_id where v.seq = 1 and c.field = 'claim'").fetchone()
            n = conn.execute("select count(*) from wb.claim").fetchone()[0]
        check("each verdict the judge wrote becomes an item; a probe does not",
              r["ok"] and [(s, v, g, c, t, q_) for s, v, g, c, t, q_, _ in rows] ==
              [("setup-1", "pass", "review", "setup", "measured", 1), ("map-3", "fail", "review", "map", "measured", 3)], (r, rows))
        check("metrics are kept as the judge measured them", rows[0][6]["wall_seconds"]["gain"] == 0.12, rows[0][6])
        check("a verdict's claim cites its record in the log", q and q[0].startswith("setup:") and q[1] == {"record": 1, "pointer": "/claim"}
              and q[2] == "morphogen:evidence.db#1", q)
        again = run_extractor(cli.connect, plugins, "substrate:morphogen", {"log": str(log)})
        with cli.connect() as conn:
            n2 = conn.execute("select count(*) from wb.claim").fetchone()[0]
        check("reading the log again adds nothing", again["ok"] and n2 == n, (n, n2))

        ev.append(verdict("later", "e" * 40, "f" * 40, True))
        c = sqlite3.connect(log)
        raw = json.loads(c.execute("select raw from evidence where seq = 3").fetchone()[0])
        raw["verdict"] = "pass"                                   # someone edits a verdict after the fact,
        for (name,) in c.execute("select name from sqlite_master where type = 'trigger'").fetchall():
            c.execute(f'drop trigger "{name}"')                   # first removing Morphogen's append-only guard
        c.execute("update evidence set raw = ? where seq = 3", (json.dumps(raw, sort_keys=True, separators=(",", ":")),))
        c.commit(); c.close()
        bad = run_extractor(cli.connect, plugins, "substrate:morphogen", {"log": str(log)})
        with cli.connect() as conn:
            later = conn.execute("select count(*) from content.verdict where cell = 'later'").fetchone()[0]
            still = conn.execute("select verdict from content.verdict where seq = 3").fetchone()[0]
        check("a tampered log is refused, and nothing from it is kept", not bad["ok"] and "broken at record 3" in bad["error"]
              and later == 0 and still == "fail", bad.get("error"))
    finally:
        with psycopg.connect(cli.url("postgres"), autocommit=True) as conn:
            conn.execute(sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(DB)))

print(f"{sum(checks)}/{len(checks)} checks passed")
sys.exit(0 if all(checks) else 1)
