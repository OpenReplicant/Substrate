"""The papers package's judged run (Morphogen: the cell's `run`; docs/contracts/environment.md, "The run").

For each case it resets the environment, steps until the episode ends (the handlers plugin's step loop, the same one the
live run uses) and prints one JSON line:

    {"id", "end": terminated|truncated|escalated, "steps", "final", "actions", "calls"}

Judged, it reads MORPHOGEN_INPUTS/cases.jsonl and calls the model at MORPHOGEN_GATEWAY with the one key the run holds
(WB_GATEWAY_KEY). A paper needs no fetch, so there is no record to replay and no network. Outside a judged run:

    python3 packages/papers/driver.py --cases packages/papers/cases/dev.jsonl

After the last case it prints a closing line, {"episodes": N}: Morphogen takes a run's last JSON line as what the run
reports about itself and keeps it from the scorer (S-110), so a driver that ended on a case would lose that case.
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


def run(items: list[dict], record, agent: dict, gateway, spec: dict = environment.SPEC):
    """Each case's line, in order. `record` is unused (the argument the other packages' drivers take); `agent` is an
    agent file's content, its handlers made fresh for the run."""
    order, entries = episode.route(HERE, agent, (spec.get("model") or {}).get("agent"), gateway)
    private = set(spec.get("private") or [])
    for case in items:
        env = environment.make(None, spec)
        shown = {k: v for k, v in case.items() if k not in private}      # the case as the environment may know it
        r = episode.run(env, shown, order, entries, max_steps=env.max_steps)
        yield {"id": case["id"], "end": r["end"], "steps": r["steps"], "final": r["final"], "actions": r["actions"],
               "calls": [{"handler": c.handler, "kind": c.kind, "reason": c.reason, "seconds": round(c.seconds, 3),
                          **{k: (c.meta or {}).get(k) for k in ("gateway_call", "usage", "model") if (c.meta or {}).get(k)}} for c in r["calls"]]}


def run_batched(items: list[dict], agent: dict, gateway, per_call: int, spec: dict = environment.SPEC, waits=(30, 60, 120)):
    """`per_call` papers to a model call (agent.yaml, parameters): the step loop carries one input an episode, so the batch is made
    here, with the same reading and the same gate (plugin/papers_records.read_batch). A paper the answer skipped is asked again in
    a later call, up to twice; one still skipped, or whose call failed, ends as escalated with no action. The call's tokens are on
    the first line of its batch."""
    sys.path.insert(0, str(HERE / "plugin"))
    import papers_records as pr
    import reading
    cfg = agent["handlers"]["main"]
    fixed, model = reading.instructions(HERE, cfg), (spec.get("model") or {}).get("agent") or cfg["model"]
    private = set(spec.get("private") or [])
    done, pending = {}, [{**{k: v for k, v in c.items() if k not in private}, "slug": c["id"]} for c in items]
    for _ in range(3):
        later = []
        for k in range(0, len(pending), per_call):
            chunk = pending[k:k + per_call]
            r = pr.read_batch(chunk, fixed, model, gateway, "handler:main", int(cfg.get("max_tokens", 700)), waits=waits)
            call = {"handler": "main", "kind": "answer" if "error" not in r else "escalate", "reason": r.get("error"), "seconds": 0,
                    "gateway_call": r.get("call"), "model": model, **({"usage": r["usage"]} if r.get("usage") else {})}
            first = True
            for p in chunk:
                if "error" in r or p["id"] in r["skipped"]:
                    later.append(p) if "error" not in r else done.setdefault(p["id"], {"end": "escalated", "steps": 0, "final": None, "actions": [], "calls": [call] if first else []})
                else:
                    done[p["id"]] = {"end": "terminated", "steps": 1, "final": r["finals"][p["id"]], "actions": [r["actions"][p["id"]]],
                                     "calls": [call] if first else []}
                first = False
        pending = later
    for p in pending:
        done[p["id"]] = {"end": "escalated", "steps": 0, "final": None, "actions": [], "calls": []}
    for c in items:
        yield {"id": c["id"], **done[c["id"]]}


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    inputs = os.environ.get("MORPHOGEN_INPUTS")
    a.add_argument("--cases", type=Path, default=Path(inputs) / "cases.jsonl" if inputs else None)
    a.add_argument("--agent", type=Path, default=HERE / "agent.yaml")
    a.add_argument("--per_call", type=int, help="papers to a call, instead of agent.yaml's parameters.per_call (to measure it)")
    o = a.parse_args(argv)
    if o.cases is None:
        a.error("no cases: --cases FILE, or MORPHOGEN_INPUTS")
    gateway = hp.Gateway(os.environ.get("MORPHOGEN_GATEWAY"), None, None, key=os.environ.get("WB_GATEWAY_KEY"))
    agent = yaml.safe_load(o.agent.read_text())
    n = 0
    per_call = int(((agent.get("parameters") or {}).get("per_call") or {}).get("value") or 1)
    if o.per_call:
        per_call = o.per_call
    items = cases(o.cases)
    for line in (run_batched(items, agent, gateway, per_call) if per_call > 1 else run(items, None, agent, gateway)):
        print(json.dumps(line), flush=True)
        n += 1
    print(json.dumps({"episodes": n}), flush=True)


if __name__ == "__main__":
    main()
