"""The lookups scorer (Morphogen: the cell's `score`, run from the base outside the candidate). Reads the driver's
lines on stdin and the outcomes from MORPHOGEN_PRIVATE/outcomes.jsonl (lines {"id", "answer", ...}, as
cases/dev.outcomes.jsonl), and prints one JSON object:

    correct    the share of cases whose answer equals the recorded field, after trimming and case-folding (the
               outcome metric; floors in environment.yaml: 0 for an agent that hands everything off, 0.208 on dev
               for one that always says "yes")
    answered   the share of cases answered rather than handed off, escalated or cut short
    steps      the mean number of actions a case took

The answer is never read from the line's `final`: the scorer replays the line's `actions` against a fresh
environment from the base, on the same record with no network, and reads the answer the environment reached
(the forged-final defence, docs/contracts/environment.md "Open"). A `reward` or `score` in a line is ignored. A
line it cannot read, a missing case, a duplicate id, or actions the environment would not take, score 0.

    python3 packages/lookups/score.py --outcomes packages/lookups/cases/dev.outcomes.jsonl < lines
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import environment  # noqa: E402


def same(a, b) -> bool:
    return isinstance(a, str) and isinstance(b, str) and a.strip().casefold() == b.strip().casefold()


def replay(case: dict, actions, record) -> dict | None:
    """The environment's final state after these actions, or None if it would not take them."""
    env = environment.make(record)
    env.reset({"id": case.get("id"), "question": case.get("question", "")}, 0)
    try:
        for a in actions if isinstance(actions, list) else []:
            env.step(a)
    except RuntimeError:       # more actions than the episode allows: not a run the environment could have had
        return None
    return env.final()


def score(lines, gold: dict[str, str], cases: dict[str, dict], record) -> dict:
    got, n = {}, Counter()
    for line in lines:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if isinstance(d, dict) and isinstance(d.get("id"), str):
            n[d["id"]] += 1
            got[d["id"]] = d
    right = answered = steps = 0
    for cid, answer in gold.items():
        d = got.get(cid)
        if d is None or n[cid] > 1:
            continue
        final = replay(cases.get(cid) or {"id": cid}, d.get("actions"), record)
        if final is None:
            continue
        steps += len(d.get("actions") or [])
        if final["answer"] is not None and not final["handed_off"]:
            answered += 1
            right += same(final["answer"], answer)
    total = len(gold) or 1
    # the two counts are Morphogen's check (S-119): it refuses a run in which they differ
    return {"correct": right / total, "answered": answered / total, "steps": steps / total,
            "cases_seen": sum(1 for cid in gold if cid in got), "cases_expected": len(gold)}


def main(argv=None):
    a = argparse.ArgumentParser()
    private, inputs = os.environ.get("MORPHOGEN_PRIVATE"), os.environ.get("MORPHOGEN_INPUTS")
    a.add_argument("--outcomes", type=Path, default=Path(private) / "outcomes.jsonl" if private else None)
    a.add_argument("--cases", type=Path, default=Path(inputs) / "cases.jsonl" if inputs else HERE / "cases/dev.jsonl")
    a.add_argument("--record", type=Path, default=Path(inputs) / "fetched.jsonl.gz" if inputs else HERE / "cases/dev.fetched.jsonl.gz")
    o = a.parse_args(argv)
    if o.outcomes is None:
        a.error("no outcomes: --outcomes FILE, or MORPHOGEN_PRIVATE")
    gold = {d["id"]: d["answer"] for d in map(json.loads, filter(str.strip, o.outcomes.read_text().splitlines()))}
    cases = {d["id"]: d for d in map(json.loads, filter(str.strip, o.cases.read_text().splitlines()))} if o.cases.is_file() else {}
    print(json.dumps(score(sys.stdin, gold, cases, environment.Record(o.record))))


if __name__ == "__main__":
    main()
