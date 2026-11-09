"""substrate:interview in a throwaway database (INTERVIEW.md): a statement that quotes the person word for word
becomes their claim on the map entry, beside the map's value; one whose quote they never said, or that names
nothing on the map, is refused and raised, never recorded; a statement that differs from the map is raised for
review; taking a statement out of the transcript retracts it.

    WORKBENCH_ADMIN_URL=postgresql://postgres:...@127.0.0.1:5432/postgres python3 plugins/substrate/tests/test_interview.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "workbench"), str(ROOT / "plugins/substrate")]
os.environ["WORKBENCH_DB"] = DB = f"workbench_test_{os.getpid()}"
os.environ.setdefault("WORKBENCH_JWT_SECRET", "i-" + "z" * 40)

import psycopg  # noqa: E402
from psycopg import sql  # noqa: E402

import substrate_interview as si  # noqa: E402
from workbench import cli  # noqa: E402
from workbench.extract import Plugins, run_extractor  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print(("ok  " if ok else "FAIL"), name, "" if ok else detail)


CATALOG = """apiVersion: backstage.io/v1alpha1
kind: Component
metadata: {name: rig, description: A machine}
spec: {type: machine, owner: group:x, system: home}
"""

TRANSCRIPT = """---
system: home
person: pat
interviewer: claude-code
date: 2026-11-09
scope: this machine
---
## 1. What it is for
**claude-code:** What is this machine for?
**pat:** It's my dev box.
I build things on it, mostly
substrate.

## 2. Who else
**claude-code:** Does anyone else use it?
**pat:** No, only me.

## Statements
```yaml
- {item: component:rig, field: description, value: "The owner's dev box", quote: "It's my dev box. I build things on it", turn: 1}
- {item: component:rig, field: "annotations:substrate.dev/intent", value: "build substrate", quote: "mostly substrate", turn: 1}
- {item: component:rig, field: description, value: "A shared server", quote: "everyone uses it", turn: 2}
- {item: component:rig, field: description, value: "Only the owner's", quote: "only me", turn: 1}
- {item: component:nowhere, field: description, value: "x", quote: "only me", turn: 2}
- {item: component:rig, field: lifecycle, value: "production", quote: "claude-code", turn: 1}
```
"""

doc = si.parse(TRANSCRIPT)
got = [(r["ok"], r.get("why", "")[:30]) for r in si.check(doc)]
check("a quote stands only if the person said it, in that turn, word for word (lines and case aside)",
      [ok for ok, _ in got] == [True, True, False, False, True, False], got)
check("the interviewer's words are not the person's", "pat did not say that" in got[5][1], got[5])

try:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "catalog-info.yaml").write_text(CATALOG)
        (root / ".state/interviews/home").mkdir(parents=True)
        t = root / ".state/interviews/home/2026-11-09.md"
        t.write_text(TRANSCRIPT)
        os.environ["WB_SUBSTRATE_ROOT"] = d
        cli.migrate()
        cli.load_plugin(ROOT / "plugins/substrate")
        plugins = Plugins().load(ROOT / "plugins")
        run_extractor(cli.connect, plugins, "substrate:catalog", {})
        r = run_extractor(cli.connect, plugins, "substrate:interview", {})
        with cli.connect() as conn:
            said = conn.execute("""select c.field, c.value, c.author, c.quote, r.extractor, c.span ->> 'start_line'
                                     from wb.claim c join wb.run r on r.id = c.run_id
                                    where c.author = 'pat' and c.status = 'current' order by c.field""").fetchall()
            desc = conn.execute("select description from api.component where slug = 'rig'").fetchone()[0]
            gaps = sorted(k for (k,) in conn.execute(
                "select key from wb.decision where raised_by = 'substrate:interview' and status = 'open'").fetchall())
        check("the extractor runs", r.get("ok"), r)
        check("each statement that stands is the person's claim, quoting them, recorded by the extractor",
              [(f, a, e) for f, _, a, _, e, _ in said] == [("annotations:substrate.dev/intent", "pat", "substrate:interview"),
                                                            ("description", "pat", "substrate:interview")]
              and said[1][3] == "It's my dev box. I build things on it" and said[1][5] == "10", said)
        check("beside the map's value, not over it", desc == "A machine", desc)
        check("a difference from the map goes to review", any(k.startswith("said:component:rig:description:pat") for k in gaps), gaps)
        check("refused statements are raised, never recorded",
              sum(k.startswith("unstated:") for k in gaps) == 4 and len(said) == 2, gaps)

        t.write_text(TRANSCRIPT.replace(
            '- {item: component:rig, field: description, value: "The owner\'s dev box", quote: "It\'s my dev box. I build things on it", turn: 1}\n', ""))
        run_extractor(cli.connect, plugins, "substrate:interview", {})
        with cli.connect() as conn:
            left = conn.execute("select field from wb.claim where author = 'pat' and status = 'current'").fetchall()
        check("a statement taken out of the transcript is retracted", left == [("annotations:substrate.dev/intent",)], left)
finally:
    with psycopg.connect(cli.url("postgres"), autocommit=True) as conn:
        conn.execute(sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(DB)))

print(f"{sum(checks)}/{len(checks)} checks passed")
sys.exit(0 if all(checks) else 1)
