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


def full_verdict(cell, base, cand):
    """A record carrying every field the item keeps beyond the first set."""
    v = verdict(cell, base, cand, False)
    v["outcome"].update({"parameter_violations": ["changes the judge-owned parameter x.y (1 -> 2)"], "system": {"ran": True}})
    v.update({"labels": {"experiment": "same-candidate", "run": "1"}, "scope": [cell, "other"], "inputs": "sha256:" + "9" * 16,
              "served": {"gateway": {"meter": "m" * 64}}, "gate": {"decision": "none", "owner": "group:default/agents",
                                                                 "lifecycle": "experimental"}})
    return v


with tempfile.TemporaryDirectory() as d:
    log = Path(d) / "evidence.db"
    ev = Evidence(log)
    ev.append(verdict("setup", "a" * 40, "b" * 40, True))
    ev.append({"claim": "probe", "kind": "probe", "subject": {"system": "setup"}, "trust": "measured", "by": "judge"})
    ev.append(verdict("map", "c" * 40, "d" * 40, False))
    ev.append(full_verdict("full", "1" * 40, "2" * 40))               # seq 4
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
              [("setup-1", "pass", "review", "setup", "measured", 1), ("map-3", "fail", "review", "map", "measured", 3),
               ("full-4", "fail", "none", "full", "measured", 4)], (r, rows))
        with cli.connect() as conn:
            new = ("labels", "scope", "inputs", "meter", "owner", "lifecycle")
            cols = ", ".join(new)
            bare = conn.execute(f"select {cols}, reasons from content.verdict where seq = 1").fetchone()
            full = conn.execute(f"select {cols}, reasons from content.verdict where seq = 4").fetchone()
            cl = {f: conn.execute("select c.quote, c.span from wb.claim c join content.verdict v on v.id = c.subject_id"
                                  " where v.seq = 4 and c.field = %s", (f,)).fetchone() for f in new}
        check("a record without the new fields leaves them empty, and reasons gain nothing",
              all(x is None for x in bare[:6]) and "parameter_violations" not in bare[6] and "system" not in bare[6], bare)
        check("a record with every new field keeps each, and reasons gain parameter_violations and system",
              full[0] == {"experiment": "same-candidate", "run": "1"} and full[1] == ["full", "other"]
              and full[2] == "sha256:" + "9" * 16 and full[3] == "m" * 64 and full[4] == "group:default/agents"
              and full[5] == "experimental" and full[6]["parameter_violations"] == ["changes the judge-owned parameter x.y (1 -> 2)"]
              and full[6]["system"] == {"ran": True}, full)
        check("each new value cites its place in the record",
              [(f, cl[f] and cl[f][1]) for f in new] == [
                  ("labels", {"record": 4, "pointer": "/labels"}), ("scope", {"record": 4, "pointer": "/scope"}),
                  ("inputs", {"record": 4, "pointer": "/inputs"}), ("meter", {"record": 4, "pointer": "/served/gateway/meter"}),
                  ("owner", {"record": 4, "pointer": "/gate/owner"}), ("lifecycle", {"record": 4, "pointer": "/gate/lifecycle"})], cl)
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
