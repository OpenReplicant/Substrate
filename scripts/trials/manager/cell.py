"""The manager-prompt cell's workload and scorer for Morphogen's judge (S-224; catalog/component-manager-prompt.yaml).

    python3 -I scripts/trials/manager/cell.py run     # `run`: every held-out scenario once, in a fresh Haiku session each;
                                                      # reads $MORPHOGEN_INPUTS/cases.json (no labels); one JSON line per scenario
    python3 -I scripts/trials/manager/cell.py score   # `score`: the run's lines on stdin, the labels from $MORPHOGEN_PRIVATE/labels.json
                                                      # (only the scorer is told where it is); prints the metrics as JSON

The scoring itself is PM-1a's frozen score.py (results/pm1a-scoring-frozen.json). The prompt under judgement is the
manager.md of the working tree the judge runs in (the base's, or the candidate's). Standard library only.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def run():
    import mgr_eval as M
    import replay
    cases = json.load(open(os.path.join(os.environ["MORPHOGEN_INPUTS"], "cases.json")))
    import copy
    fx = json.load(open(os.path.join(HERE, "portfolio_fixture.json")))
    pf = copy.deepcopy(cases["portfolio"])
    for p in pf["projects"]:
        p.update(fx["projects"].get(p["id"], {}))
    pf["meter"], pf["knowledge"] = fx["meter"], fx["knowledge"]
    driver = M.make_driver(open(os.path.join(HERE, "manager.md")).read())
    for sc in cases["scenarios"]:
        fresh = replay.fresh(pf, sc)
        sco, trace, final, res = M.run_one(driver, {**sc, "expected": {"action": "ack", "project": None, "escalate": False}}, pf)
        print(json.dumps({"id": sc["id"], "is_event": "event" in sc, "portfolio": fresh, "trace": trace, "final_text": final,
                          "res": {k: res.get(k) for k in ("launch_ts", "wall_s", "tokens", "error", "offered_tools", "attempts")}}),
              flush=True)
    print(json.dumps({"closing": "end of run", "scenarios": len(cases["scenarios"])}))


def score_stdin():
    import score as S
    labels = json.load(open(os.path.join(os.environ["MORPHOGEN_PRIVATE"], "labels.json")))
    scores = []
    for line in sys.stdin:
        line = line.strip()
        if not line or "closing" in line[:20]:
            continue
        r = json.loads(line)
        sc = {"id": r["id"], "expected": labels[r["id"]], **({"event": {}} if r["is_event"] else {})}
        scores.append(S.score(sc, r["portfolio"], r["trace"], {**r["res"], "final_text": r["final_text"]}))
    out = {"cases_seen": len(scores), "cases_expected": len(labels), "routing_accuracy": S.m_routing(scores),
           "work_itself": S.m_work(scores), "delegation_recall": S.m_deleg_recall(scores),
           "escalation_recall": S.m_esc_recall(scores), "escalation_precision": S.m_esc_prec(scores)}
    print(json.dumps(out))


if __name__ == "__main__":
    {"run": run, "score": score_stdin}[sys.argv[1]]()
