"""Run manager scenarios under a prompt and score them with PM-1a's frozen scorer (score.py, hashed in
results/pm1a-scoring-frozen.json). Used by optimise.py (train and dev only), judge.py and cell.py. Standard library only."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import drivers  # noqa: E402
import replay  # noqa: E402
import score as S  # noqa: E402


def load_portfolio(cases_path):
    """(scenarios, portfolio) from a scenarios file with the fixture laid over, as replay.load_world."""
    return replay.load_world(cases_path)


def run_one(driver, sc, portfolio):
    """One scenario in a fresh session against a fresh portfolio: (score dict, trace, final text, result)."""
    pf = replay.fresh(portfolio, sc)
    with tempfile.TemporaryDirectory(prefix="pm-cell-") as d:
        trace_path = os.path.join(d, "trace.jsonl")
        try:
            res = driver.run(S.message_for(sc), pf, trace_path)
        except drivers.RateLimited:
            raise
        except Exception as e:  # a timeout costs this scenario, not the run
            res = {"final_text": "", "launch_ts": 0.0, "wall_s": 0.0, "tokens": drivers.tokens(), "offered_tools": [],
                   "attempts": [], "error": f"{type(e).__name__}: {e}"[:300], "model": getattr(driver, "model", "")}
        trace = S.load_trace(trace_path)
    return S.score(sc, pf, trace, res), trace, res.get("final_text", ""), res


def run_many(driver, scs, portfolio, workers=3):
    with ThreadPoolExecutor(workers) as ex:
        return list(ex.map(lambda sc: run_one(driver, sc, portfolio), scs))


def make_driver(prompt_text, model="haiku", effort="low"):
    import claude_driver
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, prefix="manager-prompt-")
    f.write(prompt_text)
    f.close()
    try:
        return claude_driver.ClaudeCode(model, effort, f.name)  # reads the file now
    finally:
        os.unlink(f.name)


def objective(sco):
    """The optimiser's per-scenario score, from the frozen scorer's fields alone: 1 if the routing is right and the
    manager did not do the work itself, else 0."""
    return 1.0 if sco["routing_ok"] and not sco["worked_itself"] else 0.0


def summary(scores):
    return {"n": len(scores), "routing": S.m_routing(scores), "deleg_recall": S.m_deleg_recall(scores),
            "work_itself": S.m_work(scores), "esc_precision": S.m_esc_prec(scores), "esc_recall": S.m_esc_recall(scores),
            "tokens": S.m_tokens(scores), "latency_median_s": S.m_latency(scores)}


def explain(sc, sco, trace, final):
    """A failure in words, from the trace and the labels, for the reflection model: (text, calls)."""
    e = sc["expected"]
    allowed = [e["action"], *e.get("also", [])]
    calls = []
    for c in trace:
        if "tool" in c:
            a = json.dumps(c["arguments"], ensure_ascii=False)
            calls.append(f"{c['tool']}({a[:260]})" + (" [call failed]" if c.get("error") else ""))
    who = "a supervisor event" if "event" in sc else "the person's message"
    L = [f"Input was {who}. Expected action: {' or '.join(allowed)}; expected project: {e['project'] or 'none (not scored)'}"
         + ("; the person had to be asked or told." if e.get("escalate") else "; no need to bother the person.")]
    L.append(f"The manager did: {'+'.join(sco['tags'])}; projects named: {', '.join(sco['named']) or 'none'}.")
    if sco["routing_ok"] and not sco["worked_itself"]:
        L.append("This was routed correctly.")
    else:
        if not sco["action_ok"]:
            L.append(f"WRONG ACTION: it took '{'+'.join(sco['tags'])}' where '{' or '.join(allowed)}' was right.")
        if sco["project_ok"] is False:
            L.append(f"WRONG PROJECT: named {sco['named']}, expected {e['project']}.")
        if sco["worked_itself"]:
            L.append("It did the work itself (a tool outside its set, or more than 10 lines of code).")
        if sco["should_delegate"] and not sco["delegated"]:
            L.append("It should have delegated (started, messaged or stopped a worker) and did not.")
        if sco["failed_calls"]:
            L.append(f"{sco['failed_calls']} tool call(s) failed (see the calls).")
    if e.get("kind") == "judge":
        L.append("The label requires a judge worker (kind judge) to be started.")
    if e.get("gate"):
        L.append("The label marks this as gated work: start it, and tell the person it needs their gate.")
    return "\n".join(L), calls
