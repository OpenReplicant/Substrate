"""Trial for spec step 10: does a BPMN tool open the business plugin's files? The demo process as drawn, its export
from Workbench, and a process mapped without a diagram, exported with a layout; each read by bpmn-moddle (check.mjs).

    python3 scripts/trials/bpmn-opens/run.py FILE.bpmn...     # results to .state/trials/bpmn-opens/results.json

It runs Node in a container (CONTAINER_ENGINE, podman by default), pinned: node 24.22.1 and bpmn-moddle 10.3.1.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
IMAGE = "docker.io/library/node:24.22.1-trixie-slim"
MODDLE = "bpmn-moddle@10.3.1"

files = [Path(f).resolve() for f in sys.argv[1:]]
if not files:
    sys.exit(__doc__)
engine = os.environ.get("CONTAINER_ENGINE", "podman")
mounts = []
for n, f in enumerate(files):
    mounts += ["-v", f"{f}:/in/{n}-{f.name}:ro"]
cmd = [engine, "run", "--rm", "-v", f"{HERE / 'check.mjs'}:/w/check.mjs:ro", *mounts, IMAGE, "sh", "-c",
       f"cd /w && npm install --silent --no-audit --no-fund {MODDLE} >/dev/null 2>&1 && node check.mjs /in/*"]
p = subprocess.run(cmd, capture_output=True, text=True)
rows = [json.loads(ln) for ln in p.stdout.splitlines() if ln.startswith("{")]
out = ROOT / ".state/trials/bpmn-opens"
out.mkdir(parents=True, exist_ok=True)
(out / "results.json").write_text(json.dumps({"image": IMAGE, "parser": MODDLE, "files": rows}, indent=1))
for r in rows:
    print(("ok  " if r["ok"] else "FAIL"), r["file"], f"{r['drawn']}/{r['elements']} drawn", "; ".join(r["warnings"]))
if p.returncode and not rows:
    print(p.stderr[-1500:])
sys.exit(p.returncode)
