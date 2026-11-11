"""The scorer for bench/run.py (Morphogen: the cell's `score`, run from the base, outside the candidate): reads the
run's lines on stdin and the held-out outcomes from MORPHOGEN_PRIVATE/outcomes.json ({case id: value}), and prints
    balanced  the mean, over the outcome values, of the share of that value's cases answered rightly; an escalation
              counts as not right. A constant answer scores 1 / (number of values), however lopsided the cases
    answered  the share of the held-out cases the handler answered rather than escalated
    accuracy  the share answered rightly
"""
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

gold = json.loads((Path(os.environ["MORPHOGEN_PRIVATE"]) / "outcomes.json").read_text())
got = {}
for line in sys.stdin:
    line = line.strip()
    if line.startswith("{"):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if isinstance(d, dict) and "id" in d:
            got[d["id"]] = d
by_value, right = defaultdict(int), defaultdict(int)
answered = 0
for cid, value in gold.items():
    by_value[value] += 1
    g = got.get(cid) or {}
    if g.get("kind") == "answer":
        answered += 1
        if g.get("answer") == value:
            right[value] += 1
n = len(gold) or 1
print(json.dumps({"balanced": sum(right[v] / by_value[v] for v in by_value) / (len(by_value) or 1),
                  "answered": answered / n, "accuracy": sum(right.values()) / n}))
