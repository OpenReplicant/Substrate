"""PM-1a's scoring: a scenario's trace against its labels, paired intervals between two arms, and the falsifier.

Definitions (docs/manager-agent.md, "Measured, per arm"; where the design left a choice, it is made here):

- tags: what the trace did. A successful pm_worker_start/message/stop, pm_decision_open, desktop_ask give the tags
  start, message, stop, decision, ask. With none of those, the tag is `answer` if the person was told anything
  (desktop_say; for a person's message also the session's closing text when no desktop_say was called), else `ack`.
- action_ok: at least one tag, and every tag is the expected action or one of `also`. (`queued` in `also` allows a
  reply with no start.) A scenario that labels a start `kind: judge` needs a start of that kind.
- project_ok: (an `ack` that did nothing is not scored) the projects the trace named (arguments of start, note, decision, a worker's project for message
  and stop, pm_portfolio/kernel_search project, and, for an answer with none of these, a project id in the reply)
  are exactly the expected one. Scenarios with `project: null` are not scored on project.
- routing_ok: project_ok (where scored) and action_ok. This is the "routing-and-delegation accuracy" of falsifier 1.
- delegation: of scenarios whose expected action is start, message or stop, the share where a delegating call was
  made; and delegations made where none of start, message, stop was an allowed action.
- escalated: for a person's message, a decision opened or a question asked (a start labelled `gate` also counts
  when the person was told); for a supervisor event, any of those or a reply. It is expected when the label says
  so, or when the action taken is one the label allows as `also` (ask, decision).
- work attempts: a tool call outside the offered set, a reply with more than 10 lines of code, a failed call.
"""
from __future__ import annotations

import json
import random
import re
import statistics

DELEGATING = {"start", "message", "stop"}
TAG = {"pm_worker_start": "start", "pm_worker_message": "message", "pm_worker_stop": "stop",
       "pm_decision_open": "decision", "desktop_ask": "ask"}
FIELDS = ["objective", "output", "boundaries", "done_when"]


def load_trace(path):
    try:
        with open(path) as f:
            return [json.loads(l) for l in f if l.strip()]
    except FileNotFoundError:
        return []


def code_lines(text: str) -> int:
    n = 0
    for m in re.finditer(r"```[^\n]*\n(.*?)(?:```|$)", text or "", re.S):
        n += len([l for l in m.group(1).splitlines() if l.strip()])
    return n


def message_for(sc: dict) -> str:
    if "event" in sc:
        e = {k: v for k, v in sc["event"].items() if k != "signal"}
        return f'<channel signal="{sc["event"]["signal"]}">\n{json.dumps(e)}\n</channel>'
    return sc["message"]


def score(sc: dict, portfolio: dict, trace: list, res: dict) -> dict:
    exp = sc["expected"]
    ok_calls = [c for c in trace if "tool" in c and not c.get("error")]
    bad_calls = [c for c in trace if "tool" in c and c.get("error")]
    workers = {w["id"]: w["project"] for w in portfolio["workers"]}
    for c in ok_calls:  # a started worker belongs to its project from then on
        if c["tool"] == "pm_worker_start":
            workers[json.loads(c["result"])["worker"]] = c["arguments"]["project"]
    said = [c["arguments"].get("text", "") for c in ok_calls if c["tool"] == "desktop_say"]
    final = res.get("final_text") or ""
    tags = []
    for c in ok_calls:
        t = TAG.get(c["tool"])
        if t:
            tags.append(t)
    # the session's closing text is the reply to a person's message (the harness forwards it); a supervisor event has no
    # one to forward it to, so only desktop_say tells the person there
    told = bool(said) or ("event" not in sc and bool(final.strip()))
    base = list(dict.fromkeys(tags))
    if not base:
        base = ["answer" if told else "ack"]
    allowed = {exp["action"], *exp.get("also", [])}
    if "queued" in allowed:
        allowed.add("answer")
    action_ok = all(t in allowed for t in base)
    if exp.get("kind") == "judge":
        action_ok = action_ok and any(c["tool"] == "pm_worker_start" and c["arguments"].get("kind") == "judge" for c in ok_calls)
    # projects named
    named = set()
    for c in trace:
        if "tool" in c:
            a = c["arguments"]
            if c["tool"] in ("pm_worker_message", "pm_worker_stop") and a.get("worker") in workers:
                named.add(workers[a["worker"]])
            elif a.get("project") and not c.get("error") and c["tool"] != "kernel_search":
                named.add(a["project"])
        elif c.get("_project"):
            named.add(c["_project"])
    if not named and exp["project"]:
        ids = {p["id"] for p in portfolio["projects"]}
        text = " ".join(said + [final]).lower()
        text = re.sub(r"(knowledge kernel|the kernel(?!')|kernel_search|kernel search)", " ", text)  # the tool, not the project
        named = {i for i in ids if re.search(rf"(?<![\w-]){re.escape(i)}(?![\w-])", text)}
        if "kernel" in named and not re.search(r"kernel(?:'s|\s+(?:project|repo|release|desktop))", text):
            named.discard("kernel")  # "kernel" as a word, not as the project
    project_ok = None if exp["project"] is None else (named == {exp["project"]})
    if exp["action"] == "ack" and base == ["ack"]:
        project_ok = None  # nothing was done, so no project was named; not a routing error
    routing_ok = action_ok and project_ok is not False
    # delegation
    should_delegate = exp["action"] in DELEGATING
    delegated = any(t in DELEGATING for t in base)
    false_delegation = delegated and not (allowed & DELEGATING)
    # escalation
    ev = "event" in sc
    esc = any(t in ("decision", "ask") for t in base) or (ev and bool(said)) \
        or (bool(exp.get("gate")) and "start" in base and told)
    esc_expected = bool(exp["escalate"]) or any(t in ("ask", "decision") and t in allowed and t in base for t in base)
    # work
    offered = {n for n in res.get("offered_tools", [])}
    outside = [a for a in res.get("attempts", []) if a.replace("mcp__pm__", "") not in {t for t in TAG_ALL}]
    code = max([code_lines(t) for t in said + [final]] or [0])
    # briefs
    briefs = []
    for c in ok_calls:
        if c["tool"] == "pm_worker_start":
            a = c["arguments"]
            briefs.append({"fields": sum(1 for f in FIELDS if len(str(a.get(f, "")).strip()) >= 10) / len(FIELDS),
                           "runner": a.get("runner"), "runner_ok": (a.get("runner") == exp["runner"]) if exp.get("runner") else None,
                           "args": a})
    first_reply = next((c["ts"] for c in trace if c.get("tool") in ("desktop_say", "desktop_ask") and not c.get("error")), None)
    return {
        "id": sc["id"], "kind": sc.get("kind"), "tags": base, "named": sorted(named),
        "action_ok": action_ok, "project_ok": project_ok, "routing_ok": routing_ok,
        "should_delegate": should_delegate, "delegated": delegated, "false_delegation": false_delegation,
        "escalated": esc, "escalate_expected": esc_expected, "must_escalate": bool(exp["escalate"]),
        "outside_tools": outside, "code_reply": code > 10, "failed_calls": len(bad_calls),
        "tool_calls": len(ok_calls) + len(bad_calls), "text_only_reply": bool(final.strip()) and not said and "event" not in sc,
        "briefs": briefs, "latency_s": (first_reply - res["launch_ts"]) if first_reply else None,
        "wall_s": res["wall_s"], "tokens": res["tokens"], "error": res.get("error"),
        "worked_itself": bool(outside) or code > 10,
        "offered_ok": offered <= {f"mcp__pm__{t}" for t in TAG_ALL} if offered else None,
    }


TAG_ALL = ["pm_portfolio", "kernel_search", "pm_project_note", "pm_worker_start", "pm_worker_message", "pm_worker_stop",
           "pm_decision_open", "desktop_ask", "desktop_say"]


# ---- metrics over a list of per-scenario scores (a resample is a list of them, repeats allowed)
def rate(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float("nan")


def m_routing(S): return rate(s["routing_ok"] for s in S)
def m_action(S): return rate(s["action_ok"] for s in S)
def m_project(S): return rate(s["project_ok"] for s in S if s["project_ok"] is not None)
def m_deleg_recall(S): return rate(s["delegated"] for s in S if s["should_delegate"])
def m_false_deleg(S): return rate(s["false_delegation"] for s in S)
def m_work(S): return sum(1 for s in S if s["worked_itself"])
def m_esc_prec(S): return rate(s["escalate_expected"] for s in S if s["escalated"])
def m_esc_recall(S): return rate(s["escalated"] for s in S if s["must_escalate"])
def m_fields(S): return rate(b["fields"] for s in S for b in s["briefs"])
def m_runner(S): return rate(b["runner_ok"] for s in S for b in s["briefs"] if b["runner_ok"] is not None)
def m_latency(S): return statistics.median([s["latency_s"] for s in S if s["latency_s"] is not None] or [float("nan")])
def m_wall(S): return statistics.mean(s["wall_s"] for s in S)
def m_tokens(S): return statistics.mean(s["tokens"]["total_input"] + s["tokens"]["output"] for s in S)
def m_calls(S): return statistics.mean(s["tool_calls"] for s in S)


METRICS = [  # key, label, fn, fmt, is_rate
    ("routing", "Routing accuracy (project and action)", m_routing, "pct"),
    ("action", "Action accuracy", m_action, "pct"),
    ("project", "Project accuracy (where labelled)", m_project, "pct"),
    ("deleg", "Delegation recall (start/message/stop when expected)", m_deleg_recall, "pct"),
    ("falsedeleg", "Delegated when it should not have", m_false_deleg, "pct"),
    ("work", "Did the work itself (scenarios: outside tool or >10 lines of code)", m_work, "n"),
    ("escp", "Escalation precision", m_esc_prec, "pct"),
    ("escr", "Escalation recall", m_esc_recall, "pct"),
    ("fields", "Brief fields present (objective, output, boundaries, done_when)", m_fields, "pct"),
    ("runner", "Runner as labelled (where labelled)", m_runner, "pct"),
    ("lat", "Reply latency, median s (launch to first desktop_say/ask)", m_latency, "s"),
    ("wall", "Session wall time, mean s", m_wall, "s"),
    ("tok", "Tokens per scenario, mean (all input + output)", m_tokens, "int"),
    ("calls", "Tool calls per scenario, mean", m_calls, "f"),
]


def boot(fn, A, B=None, n=10000, seed=223):
    """95% percentile interval of fn(A) (or of fn(A) - fn(B), paired by scenario) over resamples of scenarios."""
    rng = random.Random(seed)
    N, out = len(A), []
    for _ in range(n):
        idx = [rng.randrange(N) for _ in range(N)]
        a = fn([A[i] for i in idx])
        if B is None:
            v = a
        else:
            v = a - fn([B[i] for i in idx])
        if v == v:
            out.append(v)
    out.sort()
    if not out:
        return (float("nan"), float("nan"))
    return out[int(0.025 * len(out))], out[int(0.975 * len(out)) - 1]


def falsifier(H, S):
    """'Haiku is reliable enough' against the design's four tests; PM-1b's (test 4, and the live part of 2) is not run."""
    lo, hi = boot(m_routing, H, S)
    d = m_routing(H) - m_routing(S)
    t1 = {"diff": d, "ci": (lo, hi)}
    if d < -0.05 and hi < 0:
        t1["verdict"] = "refuted"
    elif lo > -0.05:
        t1["verdict"] = "not refuted (the interval excludes a 5-point gap)"
    else:
        t1["verdict"] = "not settled"
    work = m_work(H)
    t2 = {"n": work, "verdict": "refuted" if work > 1 else "not refuted (replay only)"}
    miss = sum(1 for h, s in zip(H, S) if h["must_escalate"] and not h["escalated"] and s["must_escalate"] and s["escalated"])
    t3 = {"n": miss, "verdict": "refuted" if miss > 1 else "not refuted (one run, not a majority of three)"}
    refuted = [k for k, t in (("1", t1), ("2", t2), ("3", t3)) if t["verdict"] == "refuted"]
    if refuted:
        overall = "refuted by test " + ", ".join(refuted)
    elif t1["verdict"] == "not settled":
        overall = "unsettled (test 1's interval is too wide; test 4 is PM-1b's and was not run)"
    else:
        overall = "not refuted on PM-1a's tests; unsettled until test 4 (PM-1b) runs"
    return {"t1": t1, "t2": t2, "t3": t3, "overall": overall}


def fmt(kind, v):
    if v != v:
        return "n/a"
    return {"pct": f"{100 * v:.1f}%", "n": f"{v:.0f}", "s": f"{v:.1f}", "int": f"{v:,.0f}", "f": f"{v:.2f}"}[kind]


def fmt_ci(kind, lo, hi, diff=False):
    if lo != lo:
        return "n/a"
    if kind == "pct":
        return f"[{100 * lo:+.1f}, {100 * hi:+.1f}] pt" if diff else f"[{100 * lo:.0f}, {100 * hi:.0f}]%"
    return f"[{lo:+.1f}, {hi:+.1f}]" if diff else f"[{lo:.1f}, {hi:.1f}]"


def table(names, scores):
    """Markdown rows: each arm's value with its own interval; and, with two arms, the paired difference."""
    a, b = names
    A, B = scores[a], scores[b]
    out = [f"| Metric | {a} | {b} | {a} minus {b}, paired 95% |", "|---|---|---|---|"]
    for key, label, fn, kind in METRICS:
        row = [label]
        for S in (A, B):
            lo, hi = boot(fn, S, n=2000)
            row.append(f"{fmt(kind, fn(S))} {fmt_ci(kind, lo, hi)}")
        d = fn(A) - fn(B)
        lo, hi = boot(fn, A, B, n=2000)
        row.append(f"{(f'{100 * d:+.1f} pt' if kind == 'pct' else f'{d:+.1f}')} {fmt_ci(kind, lo, hi, True)}" if d == d else "n/a")
        out.append("| " + " | ".join(row) + " |")
    return "\n".join(out)
