"""Freeze PM-1a's scoring for the manager-prompt cell (S-224): hash the files whose content decides a score, and
check them again before any optimisation or judging run.

    python3 -I freeze.py write     # once, before the first optimisation call: writes results/pm1a-scoring-frozen.json
    python3 -I freeze.py check     # exits 1 if any frozen file has changed
"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "results", "pm1a-scoring-frozen.json")
FILES = ["score.py", "stub_pm.py", "portfolio_fixture.json", "scenarios.json", "split.json", "scenarios-search.json"]


def sha(name):
    return hashlib.sha256(open(os.path.join(HERE, name), "rb").read()).hexdigest()


def check():
    frozen = json.load(open(PATH))["sha256"]
    return [n for n in FILES if sha(n) != frozen.get(n)]


if __name__ == "__main__":
    if sys.argv[1:] == ["write"]:
        doc = {"version": "pm1a-score-2026-11-27", "sha256": {n: sha(n) for n in FILES}}
        json.dump(doc, open(PATH, "w"), indent=1)
        print(json.dumps(doc, indent=1))
    else:
        bad = check()
        print("frozen files unchanged" if not bad else f"CHANGED: {bad}")
        sys.exit(1 if bad else 0)
