"""PM-1a's scoring and stub, with a fake driver (no model calls): scripts/trials/manager/. Run: python3 -I scripts/tests/test_manager_trial.py"""
import json
import os
import subprocess
import sys
import tempfile

M = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "trials", "manager")
sys.path.insert(0, M)
import claude_driver  # noqa: E402
import drivers  # noqa: E402
import replay  # noqa: E402
import score  # noqa: E402
import stub_pm  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print(("ok    " if ok else "FAIL  ") + name + ("" if ok else f"  {detail}"))


def brief(project, runner="local", **kw):
    return {"project": project, "runner": runner, "objective": "do the thing for a reason", "output": "a draft pull request",
            "boundaries": "do not merge or tag", "done_when": "its own command passes", **kw}


def perfect(text):
    """What a manager that follows the labels would do, keyed by message text (the scenarios' own labels)."""
    for s in SC:
        if replay.S.message_for(s) == text:
            e = s["expected"]
            a = e["action"]
            if a == "start":
                return [("pm_portfolio", {}), ("pm_worker_start", brief(e["project"], e.get("runner", "local"), **({"kind": "judge"} if e.get("kind") else {})))
                        ] + ([] if s.get("event") else [("desktop_say", {"text": "started"})]) + ([("desktop_say", {"text": "waits in Review"})] if e.get("gate") else [])
            if a == "message":
                return [("pm_worker_message", {"worker": e["worker"], "text": "do it"})]
            if a == "stop":
                return [("pm_worker_stop", {"worker": e["worker"]})]
            if a == "decision":
                return [("pm_decision_open", {"kind": "question", "text": "?", **({"project": e["project"]} if e["project"] else {})})]
            if a == "ask":
                return [("desktop_ask", {"question": "which?"})]
            if a == "answer":
                return [("pm_portfolio", {"project": e["project"]} if e["project"] else {}), ("desktop_say", {"text": "here"})]
            return []
    raise KeyError(text)


SC, PF = replay.load_world()
with tempfile.TemporaryDirectory() as d:
    out = os.path.join(d, "perfect.json")
    runs, stopped = replay.run_all(drivers.Fake(perfect), SC, PF, out, log=lambda s: None)
    sc = [r["score"] for r in runs]
    check("43 scenarios replayed", len(runs) == 43 and not stopped)
    bad = [s["id"] for s in sc if not s["routing_ok"]]
    check("a manager that follows every label routes 43 of 43", not bad, bad)
    check("and escalates exactly the 14 that must", sum(s["must_escalate"] for s in sc) == 14 and score.m_esc_recall(sc) == 1.0 and score.m_esc_prec(sc) == 1.0,
          (score.m_esc_recall(sc), score.m_esc_prec(sc)))
    check("and never works itself", score.m_work(sc) == 0)
    check("its briefs have every field", score.m_fields(sc) == 1.0)
    check("its runners are as labelled", score.m_runner(sc) == 1.0, score.m_runner(sc))

    def lazy(text):
        return [("desktop_say", {"text": "I will handle it\n```\n" + "\n".join("x = 1" for _ in range(12)) + "\n```"})]
    runs2, _ = replay.run_all(drivers.Fake(lazy), SC, PF, os.path.join(d, "lazy.json"), log=lambda s: None)
    sc2 = [r["score"] for r in runs2]
    check("a manager that only talks fails delegation", score.m_deleg_recall(sc2) == 0.0)
    check("and is flagged for code in every reply", score.m_work(sc2) == 43)
    check("and misses escalations", score.m_esc_recall(sc2) < 0.5 or score.m_esc_recall(sc2) == 0.0)

    def cheat(text):
        return [("Bash", {"command": "ls"}), ("pm_worker_start", brief("metasoar"))]
    runs3, _ = replay.run_all(drivers.Fake(cheat), SC, PF, os.path.join(d, "cheat.json"), only={"s01", "s30"}, log=lambda s: None)
    check("an attempt at a tool outside the set is counted", all(r["score"]["outside_tools"] == ["Bash"] for r in runs3))
    check("a start where only an answer is allowed is a false delegation", runs3[0]["score"]["false_delegation"])
    check("a worker started to merge is wrong for s30", not runs3[1]["score"]["routing_ok"])

    # the report with two arms
    p1, p2 = os.path.join(d, "pm1a-x-good.json"), os.path.join(d, "pm1a-x-lazy.json")
    os.replace(out, p1)
    os.replace(os.path.join(d, "lazy.json"), p2)
    txt = replay.report([p2, p1])
    check("the report names the verdict", "Falsifier" in txt and "Verdict: refuted" in txt, txt[:300])
    f = score.falsifier(sc, sc)
    check("identical arms are not refuted", "refuted by" not in f["overall"], f)

# the stub: protocol, refusals, trace
with tempfile.TemporaryDirectory() as d:
    pf, tr = os.path.join(d, "pf.json"), os.path.join(d, "t.jsonl")
    json.dump(PF, open(pf, "w"))
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "pm_worker_start", "arguments": brief("metasoar")}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "pm_worker_start", "arguments": {"project": "nope"}}},
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "Bash", "arguments": {"command": "ls"}}}]
    p = subprocess.run([sys.executable, "-I", os.path.join(M, "stub_pm.py"), "--portfolio", pf, "--trace", tr],
                       input="\n".join(json.dumps(m) for m in msgs) + "\n", capture_output=True, text=True, timeout=30)
    rs = [json.loads(l) for l in p.stdout.splitlines()]
    names = [t["name"] for t in rs[1]["result"]["tools"]]
    check("the server offers the manager's tools and no others", sorted(names) == sorted(stub_pm.NAMES) and not any(n in names for n in ("Bash", "Edit", "Read", "Write")), names)
    check("a start returns a worker id", json.loads(rs[2]["result"]["content"][0]["text"])["worker"] == "w-31", rs[2])
    check("a start with a missing field or unknown project is an error", rs[3]["result"]["isError"])
    check("an unknown tool is an error", rs[4]["result"]["isError"])
    tl = [json.loads(l) for l in open(tr)]
    check("every call is traced with its arguments", len(tl) == 3 and tl[0]["arguments"]["project"] == "metasoar" and tl[0]["tool"] == "pm_worker_start", tl)
    check("the stub changes no file but the trace", sorted(os.listdir(d)) == ["pf.json", "t.jsonl"], os.listdir(d))

# the claude driver's command line and parser
cc = claude_driver.ClaudeCode("haiku")
argv = cc.argv("/x/mcp.json")
check("claude flags: no built-in tools, strict MCP, no user settings", argv[argv.index("--tools") + 1] == "" and "--strict-mcp-config" in argv and argv[argv.index("--setting-sources") + 1] == "local" and "--bare" not in argv and not any("api" in a.lower() and "key" in a.lower() for a in argv), argv)
stream = "\n".join(json.dumps(e) for e in [
    {"type": "system", "subtype": "init", "tools": ["mcp__pm__desktop_say"], "model": "claude-haiku-5-5"},
    {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "mcp__pm__desktop_say", "input": {}}, {"type": "tool_use", "name": "Bash", "input": {}}]}},
    {"type": "result", "result": "ok", "num_turns": 2, "total_cost_usd": 0.001, "usage": {"input_tokens": 3, "output_tokens": 50, "cache_read_input_tokens": 100, "cache_creation_input_tokens": 10}}])
r = claude_driver.ClaudeCode.parse(stream, "", 0)
check("the parser reads attempts, tools offered and usage", r["attempts"] == ["desktop_say", "Bash"] and r["tokens"]["total_input"] == 113 and r["offered_tools"] == ["mcp__pm__desktop_say"], r)
try:
    claude_driver.ClaudeCode.parse(json.dumps({"type": "result", "is_error": True, "result": "You've hit your session limit · resets 3:45pm"}), "", 1)
    check("a usage-limit line raises RateLimited", False)
except drivers.RateLimited:
    check("a usage-limit line raises RateLimited", True)


# the openai-compatible loop against a mock server that "thinks" unless the empty-thinking prefill is there
import http.server  # noqa: E402
import threading  # noqa: E402


class Mock(http.server.BaseHTTPRequestHandler):
    seen = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Mock.seen.append(body)
        m = body["messages"]
        pre = m[-1]["role"] == "assistant" and m[-1]["content"] == drivers.EMPTY_THINKING
        if (m[-2] if pre else m[-1])["role"] == "tool":
            msg = {"role": "assistant", "content": "done"}
        elif pre:
            msg = {"role": "assistant", "content": None, "tool_calls": [{"id": "1", "type": "function", "function": {
                "name": "desktop_say", "arguments": json.dumps({"text": "hi"})}}]}
        else:
            msg = {"role": "assistant", "content": ""}
        out = json.dumps({"choices": [{"message": msg}], "usage": {"prompt_tokens": 10, "completion_tokens": 5}}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


srv = http.server.HTTPServer(("127.0.0.1", 0), Mock)
threading.Thread(target=srv.serve_forever, daemon=True).start()
with tempfile.TemporaryDirectory() as d:
    tp = os.path.join(d, "t.jsonl")
    drv = drivers.OpenAICompatible(f"http://127.0.0.1:{srv.server_port}", "slow", prefill="auto")
    res = drv.run("hello", PF, tp)
    tr = score.load_trace(tp)
    check("auto prefill switches after an empty turn and the tool call reaches the stub", drv.prefill == "on" and [c["tool"] for c in tr] == ["desktop_say"] and res["final_text"] == "done", (drv.prefill, tr))
    check("the loop sums usage and sends the manager's tool schemas", res["tokens"]["output"] == 10 and len(Mock.seen[-1]["tools"]) == 9, res["tokens"])
    plain = drivers.OpenAICompatible(f"http://127.0.0.1:{srv.server_port}", "fast", extra={"chat_template_kwargs": {"enable_thinking": False}})
    plain.run("hello", PF, os.path.join(d, "t2.jsonl"))
    check("the extra request fields are sent", Mock.seen[-1]["chat_template_kwargs"] == {"enable_thinking": False})
srv.shutdown()

# the paired bootstrap
A = [{"routing_ok": True}] * 30 + [{"routing_ok": False}] * 13
B = [{"routing_ok": True}] * 40 + [{"routing_ok": False}] * 3
lo, hi = score.boot(score.m_routing, A, B, n=2000)
check("a paired interval for a 25-point gap lies below zero", hi < 0 and lo < -0.1, (lo, hi))

print(f"{sum(checks)}/{len(checks)} checks passed")
sys.exit(0 if all(checks) else 1)
