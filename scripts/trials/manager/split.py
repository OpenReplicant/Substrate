"""The fixed split of PM-1a's 43 scenarios for the manager-prompt cell (S-224): about 20 train, 10 dev, 13 held out.

Stratified by expected action (answer, start, message, stop, ask, decision, ack) with the r-series recovery cases as
a stratum of their own, shuffled with a fixed seed, and allocated by largest remainder so the three sizes are exactly
20 / 10 / 13. Run once; it writes
  - split.json              (committed) the seed, the train and dev ids, and for the held-out set only a count and the
                            digest of its sorted ids;
  - scenarios-search.json   (committed) the train and dev scenarios: the only scenario file the optimiser opens;
  - the held-out set, in two directories OUTSIDE the repository (Morphogen's convention: held-out answers are named in
    the uncommitted morphogen.local.yaml): `private/labels.json` (id -> expected, for the scorer alone) and
    `inputs/cases.json` (the portfolio and each scenario without its labels, for the workload to read).
`scenarios.json` stays as PM-1a's record of all 43; the optimiser never opens it.

    python3 -I split.py --private ~/.local/share/morphogen-private/manager-prompt \
                        --inputs  ~/.local/share/morphogen-private/manager-prompt-inputs
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = 20261127
SIZES = {"heldout": 13, "dev": 10, "train": 20}


def stratum(sc):
    return "recovery" if sc["id"].startswith("r") else sc["expected"]["action"]


def split(scenarios, seed=SEED):
    rng = random.Random(seed)
    strata = {}
    for sc in scenarios:
        strata.setdefault(stratum(sc), []).append(sc["id"])
    n = len(scenarios)
    out = {k: [] for k in SIZES}
    quota = {}
    for name, ids in sorted(strata.items()):
        rng.shuffle(ids)
        quota[name] = {k: len(ids) * SIZES[k] / n for k in ("heldout", "dev")}
    # largest remainder, held-out first, then dev, from what is left of each stratum
    take = {name: {"heldout": 0, "dev": 0} for name in strata}
    for k in ("heldout", "dev"):
        for name in strata:
            take[name][k] = int(quota[name][k])
        short = SIZES[k] - sum(take[name][k] for name in strata)
        order = sorted(strata, key=lambda s: (-(quota[s][k] - int(quota[s][k])), rng.random()))
        for name in order:
            if short <= 0:
                break
            if take[name]["heldout"] + take[name]["dev"] + 1 <= len(strata[name]) - (0 if k == "dev" else 0):
                take[name][k] += 1
                short -= 1
    for name, ids in sorted(strata.items()):
        h, d = take[name]["heldout"], take[name]["dev"]
        out["heldout"] += ids[:h]
        out["dev"] += ids[h:h + d]
        out["train"] += ids[h + d:]
    return out, strata


def digest(ids):
    return hashlib.sha256(json.dumps(sorted(ids)).encode()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", required=True)
    ap.add_argument("--inputs", required=True)
    a = ap.parse_args()
    data = json.load(open(os.path.join(HERE, "scenarios.json")))
    sc = data["scenarios"]
    out, strata = split(sc)
    assert {k: len(v) for k, v in out.items()} == SIZES, {k: len(v) for k, v in out.items()}
    assert sorted(out["heldout"] + out["dev"] + out["train"]) == sorted(s["id"] for s in sc)
    by = {s["id"]: s for s in sc}
    order = [s["id"] for s in sc]
    search = [dict(by[i], split=k) for i in order for k in ("train", "dev") if i in out[k]]
    json.dump({"about": "The train and dev scenarios of PM-1a's 43 (split.py): the only scenarios the optimiser reads. " + data["about"],
               "portfolio": data["portfolio"], "scenarios": search}, open(os.path.join(HERE, "scenarios-search.json"), "w"), indent=1)
    json.dump({"seed": SEED, "method": "stratified by expected action, r-series recovery as its own stratum; largest remainder",
               "sizes": SIZES, "strata": {k: len(v) for k, v in sorted(strata.items())},
               "train": sorted(out["train"]), "dev": sorted(out["dev"]),
               "heldout": {"count": len(out["heldout"]), "sha256_of_sorted_ids": digest(out["heldout"]),
                           "where": "outside the repository: labels in the private directory, cases in the inputs directory"}},
              open(os.path.join(HERE, "split.json"), "w"), indent=1)
    os.makedirs(a.private, exist_ok=True)
    os.makedirs(a.inputs, exist_ok=True)
    held = [by[i] for i in order if i in out["heldout"]]
    json.dump({s["id"]: s["expected"] for s in held}, open(os.path.join(a.private, "labels.json"), "w"), indent=1)
    json.dump({"portfolio": data["portfolio"], "scenarios": [{k: v for k, v in s.items() if k != "expected"} for s in held]},
              open(os.path.join(a.inputs, "cases.json"), "w"), indent=1)
    for d in (a.private, a.inputs):
        os.chmod(d, 0o700)
    print({k: len(v) for k, v in out.items()}, "held-out written outside the repository")


if __name__ == "__main__":
    main()
