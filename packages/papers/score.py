"""The papers scorer (Morphogen: the cell's `score`, run from the base outside the candidate). Reads the driver's lines on
stdin and the reference records from MORPHOGEN_PRIVATE/outcomes.jsonl (lines {"id", "answer": {...}}, as
cases/dev.outcomes.jsonl), and prints one JSON object:

    correct         the outcome metric: the mean, over cases, of four agreements, each 1 or 0 (floors in environment.yaml)
    component_kind  the share of cases whose component_kind equals the reference's
    slot            the same for slot
    result, needs   the share of cases where the sentences cited overlap the reference's: any sentence number in common agrees; a case
                    where both are empty agrees, and one empty and one not does not
    answered        the share of cases recorded rather than handed off, escalated or cut short
    floor_nothing   what an agent that hands every paper off scores on these cases
    floor_empty     what one that records every field empty scores
    floor_constant  what one that always records component_kind other and slot none, and nothing else, scores

`does` is free text and is not scored (the gate still needs its quote). A case handed off, missing, duplicated, not
readable, or whose actions the environment would not take, scores 0 on all four.

The record is never read from the line's `final`: the scorer replays the line's `actions` against a fresh environment
from the base, on the case's own abstract, and reads what the gate accepted (the forged-final defence,
docs/contracts/environment.md "Open"). A `reward` or `score` in a line is ignored. The abstracts are read from the cases
file (MORPHOGEN_INPUTS/cases.jsonl, or cases/dev.jsonl), never from the line.

    python3 packages/papers/score.py --outcomes packages/papers/cases/dev.outcomes.jsonl < lines
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

FIELDS = ("component_kind", "slot", "result", "needs")


def replay(case: dict, actions) -> dict | None:
    """The environment's final state after these actions, or None if it would not take them."""
    env = environment.make()
    env.reset({k: case.get(k) for k in ("id", "arxiv_id", "title", "abstract")}, 0)
    try:
        for a in actions if isinstance(actions, list) else []:
            env.step(a)
    except RuntimeError:       # more actions than the episode allows: not a run the environment could have had
        return None
    return env.final()


def agree(field: str, got: dict, ref: dict, abstract: str) -> int:
    """One field of one case: 1 or 0. `got` and `ref` are {field: {"value", "sentences"?, "quote"?}} as the gate holds them."""
    g, r = got.get(field), ref.get(field)
    if field in ("component_kind", "slot"):
        return int(bool(g and r and g["value"] == r["value"]))
    if not g or not r:
        return int(not g and not r)
    return int(bool(set(g.get("sentences") or []) & set(r.get("sentences") or [])))


def reference(answer: dict, abstract: str) -> dict:
    """A reference record, through the same gate: a field citing a sentence the abstract does not have is no field at all."""
    return environment.gate(answer, abstract)[0]


def score(lines, gold: dict[str, dict], cases: dict[str, dict], record=None) -> dict:
    """`record` is unused (a paper needs no recorded fetch): the argument the other packages' scorers take."""
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
    sums, answered = Counter(), 0
    for cid, answer in gold.items():
        d, case = got.get(cid), cases.get(cid) or {}
        if d is None or n[cid] > 1:
            continue
        final = replay({**case, "id": cid}, d.get("actions"))
        if final is None or final["record"] is None:
            continue
        answered += 1
        ref = reference(answer, case.get("abstract", ""))
        for f in FIELDS:
            sums[f] += agree(f, final["record"], ref, case.get("abstract", ""))
    total = len(gold) or 1
    out = {"correct": sum(sums.values()) / (total * len(FIELDS)), **{f: sums[f] / total for f in FIELDS}, "answered": answered / total}
    return out


def floors(gold: dict, cases: dict) -> dict:
    """The three agents that need no model, run through the same replay and scoring."""
    def lines(action):
        return [json.dumps({"id": cid, "actions": [action]}) for cid in gold]
    return {"floor_nothing": score(lines({"kind": "hand_off", "reason": "does nothing"}), gold, cases)["correct"],
            "floor_empty": score(lines({"kind": "record"}), gold, cases)["correct"],
            "floor_constant": score(lines({"kind": "record", **environment.SPEC["outcome"]["constant"]}), gold, cases)["correct"]}


def main(argv=None):
    a = argparse.ArgumentParser()
    private, inputs = os.environ.get("MORPHOGEN_PRIVATE"), os.environ.get("MORPHOGEN_INPUTS")
    a.add_argument("--outcomes", type=Path, default=Path(private) / "outcomes.jsonl" if private else None)
    a.add_argument("--cases", type=Path, default=Path(inputs) / "cases.jsonl" if inputs else HERE / "cases/dev.jsonl")
    o = a.parse_args(argv)
    if o.outcomes is None:
        a.error("no outcomes: --outcomes FILE, or MORPHOGEN_PRIVATE")
    gold = {d["id"]: d["answer"] for d in map(json.loads, filter(str.strip, o.outcomes.read_text().splitlines()))}
    cases = {d["id"]: d for d in map(json.loads, filter(str.strip, o.cases.read_text().splitlines()))} if o.cases.is_file() else {}
    print(json.dumps({**score(sys.stdin, gold, cases), **floors(gold, cases)}))


if __name__ == "__main__":
    main()
