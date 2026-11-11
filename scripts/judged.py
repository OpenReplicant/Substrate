#!/usr/bin/env python3
"""Cases for Morphogen's judged runs of a model handler (spec step 22, S-87), written outside the repository.

    python3 scripts/judged.py drift-gaps [HANDLER]   # the drift-gaps stream's decided gaps, for HANDLER's settings
    python3 scripts/judged.py env                    # the values judged runs are served: their database's password

Writes, under JUDGED_DIR (default ~/.local/share/substrate/judged)/STREAM:
    inputs/handler.json   the handler's slug, the stream's description and the handler's settings (streams.yaml)
    inputs/cases.jsonl    each decided input, without its outcome
    private/outcomes.json each case's outcome (held out: only Morphogen's scorer is told where it is)
and prints the lines for morphogen.local.yaml. Every decided case is held out, so no case's history may show an
outcome: an input's history is the decisions made before it arrived, and a held-out case's decision would be in
the history of every case after it, readable by the candidate. History here keeps only decisions that are not held
out (none, while every decided case is).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def api(path: str) -> list:
    token = subprocess.run([str(ROOT / "scripts/workbench.sh"), "token", "claude-code", "--hours", "0.05"],
                           capture_output=True, text=True, check=True).stdout.strip()
    req = urllib.request.Request(f"http://127.0.0.1:8080/api/{path}", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def drift_gaps(handler: str) -> tuple[dict, list, dict]:
    spec = yaml.safe_load((ROOT / "streams.yaml").read_text())["streams"]["drift-gaps"]
    h = dict(spec["handlers"][handler])
    if h.get("kind") != "model":
        raise SystemExit(f"{handler} is not a model handler of drift-gaps")
    src = spec["source"]
    rows = api(f"decisions?raised_by=eq.{src['raised_by']}&kind=eq.{src.get('decision_kind', 'gap')}"
               "&select=id,key,kind,subject,status,decided_by,created_at&order=created_at,id")
    cases, outcomes = [], {}
    for d in rows:
        if d["status"] not in ("approved", "declined") or not d.get("decided_by") or d["decided_by"] == src["raised_by"]:
            continue
        cid = f"{d['key'] or d['id']}-{str(d['id'])[:8]}"   # as handlers_plugin.from_decisions names an input
        cases.append({"id": cid, "key": d["key"] or d["id"],
                      "payload": {"decision": d["id"], "kind": d["kind"], "subject": d["subject"]}, "history": []})
        outcomes[cid] = d["status"]
    config = {k: v for k, v in h.items() if k not in ("kind", "entry", "description")}
    return {"slug": handler, "about": spec["description"], "config": config}, cases, outcomes


def run_env() -> None:
    """The values a judged run is served (Morphogen's env and services, morphogen.local.yaml): a password for the
    fresh database each run gets, and the URL its tests reach it by. Made once, mode 600; never in the repository."""
    import secrets
    f = Path(os.environ.get("JUDGED_DIR") or Path.home() / ".local/share/substrate/judged") / "run.env"
    if not f.exists():
        f.parent.mkdir(parents=True, exist_ok=True)
        pw = secrets.token_hex(16)
        f.touch(mode=0o600)
        f.write_text(f"POSTGRES_PASSWORD={pw}\nWORKBENCH_ADMIN_URL=postgresql://postgres:{pw}@db:5432/postgres\n")
    f.chmod(0o600)
    print(f"  {f}: POSTGRES_PASSWORD (the run's database), WORKBENCH_ADMIN_URL (its tests' way in)")


def main() -> None:
    if len(sys.argv) == 2 and sys.argv[1] == "env":
        return run_env()
    if len(sys.argv) < 2 or sys.argv[1] != "drift-gaps":
        print(__doc__)
        sys.exit(2)
    handler = sys.argv[2] if len(sys.argv) > 2 else "local-model"
    meta, cases, outcomes = drift_gaps(handler)
    base = Path(os.environ.get("JUDGED_DIR") or Path.home() / ".local/share/substrate/judged") / "drift-gaps"
    (base / "inputs").mkdir(parents=True, exist_ok=True)
    (base / "private").mkdir(parents=True, exist_ok=True)
    (base / "inputs/handler.json").write_text(json.dumps(meta, indent=1) + "\n")
    (base / "inputs/cases.jsonl").write_text("".join(json.dumps(c) + "\n" for c in cases))
    (base / "private/outcomes.json").write_text(json.dumps(outcomes, indent=1) + "\n")
    values = sorted(set(outcomes.values()))
    print(f"  {len(cases)} cases ({', '.join(f'{v} {list(outcomes.values()).count(v)}' for v in values)}) for {handler}, in {base}")
    print(f"  morphogen.local.yaml: cells: {{component:model-handler: {{inputs: {base / 'inputs'}, private: {base / 'private'}}}}}")


if __name__ == "__main__":
    main()
