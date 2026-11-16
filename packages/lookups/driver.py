"""The lookups package's judged run (Morphogen: the cell's `run`; docs/contracts/environment.md, "The run").

For each case it resets the environment, steps until the episode ends (the handlers plugin's step loop, the same
one the live run uses) and prints one JSON line:

    {"id", "end": terminated|truncated|escalated, "steps", "final", "actions", "calls"}

Judged, it reads MORPHOGEN_INPUTS/cases.jsonl and replays MORPHOGEN_INPUTS/fetched.jsonl.gz with no network, and
calls the model at MORPHOGEN_GATEWAY with the one key the run holds (WB_GATEWAY_KEY). Outside a judged run:

    python3 packages/lookups/driver.py --cases packages/lookups/cases/dev.jsonl     # replays cases/dev.fetched.jsonl.gz
    python3 packages/lookups/driver.py --cases FILE --record FILE --network         # reads what is not recorded, and keeps it

The operator records held-out cases this way, outside the repository, before a verdict. A page not in the record
is an observation saying so, never a network call, unless --network is given.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / "plugins/handlers")]

import environment  # noqa: E402
import episode  # noqa: E402
import handlers_plugin as hp  # noqa: E402


def cases(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def run(items: list[dict], record: environment.Record, agent: dict, gateway, spec: dict = environment.SPEC):
    """Each case's line, in order. `agent` is an agent file's content; its handlers are made fresh for the run."""
    order, entries = episode.route(HERE, agent, (spec.get("model") or {}).get("agent"), gateway)
    private = set(spec.get("private") or [])
    for case in items:
        env = environment.make(record, spec)
        shown = {k: v for k, v in case.items() if k not in private}      # the case as the environment may know it
        r = episode.run(env, shown, order, entries, max_steps=env.max_steps)
        yield {"id": case["id"], "end": r["end"], "steps": r["steps"], "final": r["final"], "actions": r["actions"],
               "calls": [{"handler": c.handler, "kind": c.kind, "reason": c.reason, "seconds": round(c.seconds, 3),
                          **{k: (c.meta or {}).get(k) for k in ("gateway_call", "usage") if (c.meta or {}).get(k)}} for c in r["calls"]]}


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    inputs = os.environ.get("MORPHOGEN_INPUTS")
    a.add_argument("--cases", type=Path, default=Path(inputs) / "cases.jsonl" if inputs else None)
    a.add_argument("--record", type=Path, help="the record to replay (default: beside the cases, or cases/dev.fetched.jsonl.gz)")
    a.add_argument("--network", action="store_true", help="read pages the record lacks, and keep them in it")
    a.add_argument("--agent", type=Path, default=HERE / "agent.yaml")
    o = a.parse_args(argv)
    if o.cases is None:
        a.error("no cases: --cases FILE, or MORPHOGEN_INPUTS")
    record_path = o.record or (Path(inputs) / "fetched.jsonl.gz" if inputs else HERE / "cases/dev.fetched.jsonl.gz")
    record = environment.Record(record_path, network=o.network)
    gateway = hp.Gateway(os.environ.get("MORPHOGEN_GATEWAY"), None, None, key=os.environ.get("WB_GATEWAY_KEY"))
    agent = yaml.safe_load(o.agent.read_text())
    try:
        n = 0
        for line in run(cases(o.cases), record, agent, gateway):
            print(json.dumps(line), flush=True)
            n += 1
        # Morphogen takes a run's last JSON line as what the run reports about itself and keeps it from the scorer
        # (S-110): without this closing line the last case would be the one it takes, and would score as missing
        print(json.dumps({"episodes": n}), flush=True)
    finally:
        if o.network and record.new:
            record.save(record_path)


if __name__ == "__main__":
    main()
