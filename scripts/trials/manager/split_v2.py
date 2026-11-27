"""The v2 split of PM-1a's scenario set (about 215 scenarios), run ONCE, after the owner has confirmed the labels in
scenarios-v2-proposed.json (see scenarios-v2-review.md). Do not run it on unconfirmed labels.

What it keeps and what it decides:
  - the 43 v1 scenarios stay where split.py put them (recomputed from the same seed, so no private file is opened); the
    13 held-out never move back;
  - a variation goes to the same split as the scenario it varies, all the way up its chain (a family never straddles
    train and held-out, or the optimiser would read a near-copy of a held-out case);
  - the other families (session paraphrases and incidents with their variations) are allocated greedily, in a fixed-seed
    order, to whichever split is furthest below its target in the strata the family's scenarios fall in. Targets: held-out
    one third of the whole, then train : dev = 2 : 1 for the rest. Strata are as split.py's (expected action, with the
    r-series recovery cases as one stratum).

Writes (next to this file) scenarios-v2.json (the confirmed set, as it was read), split-v2.json (committed: ids of train
and dev, a count and a digest for held-out) and scenarios-search-v2.json (train and dev only: what the optimiser may
open); and, outside the repository, the held-out labels and inputs, as split.py does.

    python3 -I split_v2.py --private ~/.local/share/morphogen-private/manager-prompt-v2 \
                           --inputs  ~/.local/share/morphogen-private/manager-prompt-v2-inputs
A new scoring version (pm1a-score-<date>, freeze.py) must be written for these files before any optimisation uses them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random

import split as v1

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = 20261128
SHARE = {"heldout": 1 / 3, "dev": 2 / 9, "train": 4 / 9}
NAMES = ("heldout", "dev", "train")


def root_of(sc, by):
    """The id a scenario's family hangs on: a variation's parent, followed up to a scenario that is not a variation."""
    seen = set()
    while str(sc.get("source", "")).startswith("variation-of:"):
        parent = sc["source"].split(":", 1)[1]
        if parent in seen or parent not in by:
            raise ValueError(f"{sc['id']}: bad parent {parent}")
        seen.add(parent)
        sc = by[parent]
    return sc["id"]


def allocate(scenarios, seed=SEED):
    by = {s["id"]: s for s in scenarios}
    old = json.load(open(os.path.join(HERE, "scenarios.json")))["scenarios"]
    fixed, _ = v1.split(old)
    fixed_of = {i: k for k, ids in fixed.items() for i in ids}
    fam = {}
    for s in scenarios:
        fam.setdefault(root_of(s, by), []).append(s["id"])
    for r, ids in fam.items():
        homes = {fixed_of[i] for i in ids if i in fixed_of}
        assert len(homes) <= 1, f"family {r} spans {homes}"
    n = len(scenarios)
    strata = {}
    for s in scenarios:
        strata[v1.stratum(s)] = strata.get(v1.stratum(s), 0) + 1
    target = {st: {k: c * SHARE[k] for k in NAMES} for st, c in strata.items()}
    have = {st: {k: 0 for k in NAMES} for st in strata}
    out = {k: [] for k in NAMES}

    def put(ids, k):
        for i in ids:
            out[k].append(i)
            have[v1.stratum(by[i])][k] += 1
    free = []
    for r, ids in sorted(fam.items()):
        homes = {fixed_of[i] for i in ids if i in fixed_of}
        if homes:
            put(ids, homes.pop())
        else:
            free.append(r)
    rng = random.Random(seed)
    rng.shuffle(free)
    free.sort(key=lambda r: -len(fam[r]))  # big families first, ties in the shuffled order (sort is stable)
    for r in free:
        def gap(k):
            return sum(target[v1.stratum(by[i])][k] - have[v1.stratum(by[i])][k] for i in fam[r])
        put(fam[r], max(NAMES, key=lambda k: (gap(k), rng.random())))
    assert sorted(sum(out.values(), [])) == sorted(by)
    return out


def digest(ids):
    return hashlib.sha256(json.dumps(sorted(ids)).encode()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", required=True)
    ap.add_argument("--inputs", required=True)
    ap.add_argument("--set", default=os.path.join(HERE, "scenarios-v2-proposed.json"))
    a = ap.parse_args()
    data = json.load(open(a.set))
    sc = data["scenarios"]
    low = [s["id"] for s in sc if s.get("label_confidence") != "high" and not s.get("confirmed")]
    if low:
        print(f"note: {len(low)} medium or low labels have no 'confirmed': true; confirm or fix them first if you have not")
    out = allocate(sc)
    by = {s["id"]: s for s in sc}
    order = [s["id"] for s in sc]
    json.dump(data, open(os.path.join(HERE, "scenarios-v2.json"), "w"), indent=1, ensure_ascii=False)
    search = [dict(by[i], split=k) for i in order for k in ("train", "dev") if i in out[k]]
    json.dump({"about": "The train and dev scenarios of PM-1a v2 (split_v2.py): the only scenarios the optimiser reads. " + data["about"],
               "portfolio": data["portfolio"], "scenarios": search}, open(os.path.join(HERE, "scenarios-search-v2.json"), "w"), indent=1, ensure_ascii=False)
    strata = {}
    for s in sc:
        strata[v1.stratum(s)] = strata.get(v1.stratum(s), 0) + 1
    json.dump({"seed": SEED, "method": "v1's 43 keep their split; a variation follows its parent's family; other families are placed greedily "
               "by stratum (expected action, r-series recovery separate) toward held-out 1/3, dev 2/9, train 4/9",
               "sizes": {k: len(v) for k, v in out.items()}, "strata": dict(sorted(strata.items())),
               "train": sorted(out["train"]), "dev": sorted(out["dev"]),
               "heldout": {"count": len(out["heldout"]), "sha256_of_sorted_ids": digest(out["heldout"]),
                           "where": "outside the repository: labels in the private directory, cases in the inputs directory"}},
              open(os.path.join(HERE, "split-v2.json"), "w"), indent=1)
    os.makedirs(a.private, exist_ok=True)
    os.makedirs(a.inputs, exist_ok=True)
    held = [by[i] for i in order if i in out["heldout"]]
    json.dump({s["id"]: s["expected"] for s in held}, open(os.path.join(a.private, "labels.json"), "w"), indent=1)
    json.dump({"portfolio": data["portfolio"], "scenarios": [{k: v for k, v in s.items() if k not in ("expected", "label_reason", "label_confidence", "source", "note")} for s in held]},
              open(os.path.join(a.inputs, "cases.json"), "w"), indent=1, ensure_ascii=False)
    for d in (a.private, a.inputs):
        os.chmod(d, 0o700)
    print({k: len(v) for k, v in out.items()}, "held-out written outside the repository")


if __name__ == "__main__":
    main()
