"""The verdict on the held-out scenarios: the baseline prompt and a candidate, paired by scenario, `--rounds` runs each
(S-224). It is the cell's `run` and `score` (cell.py) with the same frozen scorer, run for both prompts in alternating
order, and a paired bootstrap over scenarios; it does not replace Morphogen's judge (README, "The judge"), whose sign test
needs more rounds than this budget buys, but applies the cell's rules (catalog/component-manager-prompt.yaml).

Rule, fixed before any held-out run: KEEP the candidate only if
  (a) mean routing accuracy gain >= 5 points and the paired 95% interval over scenarios lies wholly above 0,
  (b) it did the work itself in no run (the constraint), and
  (c) delegation recall is not more than 10 points below the baseline's.
Otherwise REFUSE. The held-out content stays outside the repository: only aggregates go in the results file; the
per-scenario outcomes go to the private directory.

    python3 -I judge.py --candidate results/gepa-2026-11-27/best.md --private DIR --inputs DIR --rounds 3 --out results/judge-2026-11-27.md
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import random
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import drivers  # noqa: E402
import freeze  # noqa: E402
import mgr_eval as M  # noqa: E402
import replay  # noqa: E402
import score as S  # noqa: E402


def boot_paired(fn, A, B, n=10000, seed=223):
    """95% interval of fn(A) - fn(B) over resamples of scenario indices; A and B are lists (per scenario) of lists of runs."""
    rng = random.Random(seed)
    N = len(A)
    out = []
    for _ in range(n):
        idx = [rng.randrange(N) for _ in range(N)]
        v = fn([A[i] for i in idx]) - fn([B[i] for i in idx])
        if v == v:
            out.append(v)
    out.sort()
    return out[int(0.025 * len(out))], out[int(0.975 * len(out)) - 1]


def boot_one(fn, A, n=10000, seed=223):
    rng = random.Random(seed)
    N = len(A)
    out = sorted(fn([A[rng.randrange(N)] for _ in range(N)]) for _ in range(n))
    return out[int(0.025 * len(out))], out[int(0.975 * len(out)) - 1]


# metrics over a list of per-scenario run lists (each scenario: its runs' score dicts)
def routing(G): return statistics.mean(s["routing_ok"] for g in G for s in g)
def work(G): return sum(s["worked_itself"] for g in G for s in g)
def deleg(G):
    xs = [s["delegated"] for g in G for s in g if s["should_delegate"]]
    return statistics.mean(xs) if xs else float("nan")
def esc_r(G):
    xs = [s["escalated"] for g in G for s in g if s["must_escalate"]]
    return statistics.mean(xs) if xs else float("nan")
def esc_p(G):
    xs = [s["escalate_expected"] for g in G for s in g if s["escalated"]]
    return statistics.mean(xs) if xs else float("nan")
def tokens(G): return statistics.mean(s["tokens"]["total_input"] + s["tokens"]["output"] for g in G for s in g)
def latency(G):
    xs = [s["latency_s"] for g in G for s in g if s["latency_s"] is not None]
    return statistics.median(xs) if xs else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--baseline", default=os.path.join(HERE, "manager.md"))
    ap.add_argument("--private", required=True)
    ap.add_argument("--inputs", required=True)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    bad = freeze.check()
    if bad:
        sys.exit(f"scoring is frozen; changed: {bad}")
    labels = json.load(open(os.path.join(a.private, "labels.json")))
    cases = json.load(open(os.path.join(a.inputs, "cases.json")))
    fx = json.load(open(os.path.join(HERE, "portfolio_fixture.json")))
    pf = copy.deepcopy(cases["portfolio"])
    for p in pf["projects"]:
        p.update(fx["projects"].get(p["id"], {}))
    pf["meter"], pf["knowledge"] = fx["meter"], fx["knowledge"]
    scs = [{**sc, "expected": labels[sc["id"]]} for sc in cases["scenarios"]]
    arms = {"baseline": M.make_driver(open(a.baseline).read()), "candidate": M.make_driver(open(a.candidate).read())}
    runs = {k: [[] for _ in scs] for k in arms}
    raw, stopped = [], None
    try:
        for r in range(a.rounds):
            order = ["baseline", "candidate"] if r % 2 == 0 else ["candidate", "baseline"]
            for arm in order:
                res = M.run_many(arms[arm], scs, pf, workers=3)
                for i, (sco, trace, final, _) in enumerate(res):
                    runs[arm][i].append(sco)
                    raw.append({"round": r, "arm": arm, "id": scs[i]["id"], "tags": sco["tags"], "named": sco["named"],
                                "routing_ok": sco["routing_ok"], "worked_itself": sco["worked_itself"]})
                print(f"round {r} {arm}: routing {statistics.mean(s['routing_ok'] for s in (x[0] for x in res)):.3f}", flush=True)
    except drivers.RateLimited as e:
        stopped = f"rate limit: {e}"
    done = min(len(g) for g in runs["baseline"] + runs["candidate"])
    if done == 0:
        sys.exit(f"no complete round; {stopped}")
    A = [g[:done] for g in runs["candidate"]]
    B = [g[:done] for g in runs["baseline"]]
    json.dump(raw, open(os.path.join(a.private, "judge-raw.json"), "w"), indent=1)  # private: held-out outcomes
    rows = []
    for name, fn, kind in (("Routing accuracy (primary)", routing, "pct"), ("Delegation recall (guard)", deleg, "pct"),
                           ("Escalation recall", esc_r, "pct"), ("Escalation precision", esc_p, "pct"),
                           ("Did the work itself, runs (constraint, must be 0)", work, "n"),
                           ("Tokens per scenario, mean", tokens, "int"), ("Reply latency, median s", latency, "f")):
        row = [name]
        for G in (B, A):
            lo, hi = boot_one(fn, G, n=4000)
            row.append(S.fmt(kind, fn(G)) + (f" [{S.fmt(kind, lo)}, {S.fmt(kind, hi)}]" if kind != "n" else ""))
        d = fn(A) - fn(B)
        if kind == "n":
            row.append(f"{d:+.0f}")
        else:
            lo, hi = boot_paired(fn, A, B, n=4000)
            sc_ = 100 if kind == "pct" else 1
            row.append(f"{d * sc_:+.1f}{' pt' if kind == 'pct' else ''} [{lo * sc_:+.1f}, {hi * sc_:+.1f}]")
        rows.append("| " + " | ".join(row) + " |")
    d = routing(A) - routing(B)
    lo, hi = boot_paired(routing, A, B)
    dd = deleg(A) - deleg(B)
    a_ok, b_ok, c_ok = (d >= 0.05 and lo > 0), work(A) == 0, (dd != dd or dd >= -0.10)
    # a sign test over scenarios on the per-scenario routing means
    diffs = [statistics.mean(s["routing_ok"] for s in x) - statistics.mean(s["routing_ok"] for s in y) for x, y in zip(A, B)]
    pos, neg = sum(1 for v in diffs if v > 0), sum(1 for v in diffs if v < 0)
    from math import comb
    n = pos + neg
    p = min(1.0, 2 * sum(comb(n, k) for k in range(0, min(pos, neg) + 1)) / 2 ** n) if n else 1.0
    verdict = "KEEP" if (a_ok and b_ok and c_ok) else "REFUSE"
    why = [f"(a) routing gain {d * 100:+.1f} pt, paired 95% [{lo * 100:+.1f}, {hi * 100:+.1f}]: {'met' if a_ok else 'not met'}",
           f"(b) the candidate did the work itself in {work(A)} run(s): {'met' if b_ok else 'not met'}",
           f"(c) delegation recall change {dd * 100:+.1f} pt (limit -10): {'met' if c_ok else 'not met'}"]
    text = "\n".join([
        f"# Held-out verdict, manager prompt (S-224)", "",
        f"Held-out scenarios: {len(scs)} (outside the repository). Paired runs per scenario per arm: {done}"
        + (f" (stopped: {stopped})" if stopped else "") + ". Intervals: bootstrap over scenarios, percentile, 95%. "
        "Scorer: PM-1a's frozen score.py (hash in pm1a-scoring-frozen.json). Arms: Haiku 5.5, `claude -p`, same session, "
        "baseline = manager.md at the base; candidate = the optimised prompt.", "",
        "| Metric | baseline | candidate | candidate minus baseline, paired 95% |", "|---|---|---|---|", *rows, "",
        f"Scenarios where the candidate's mean routing was higher / lower / equal: {pos} / {neg} / {len(diffs) - n}; "
        f"two-sided sign test p = {p:.3f}.", "",
        f"**Verdict: {verdict}.**", "", *[f"- {w}" for w in why], ""])
    open(a.out, "w").write(text)
    print(text)


if __name__ == "__main__":
    main()
