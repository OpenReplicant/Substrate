"""PM-1a's drivers: one interface, three ways to put a message to a manager (docs/manager-agent.md, section 8).

    driver.run(text, portfolio, trace_path) -> dict
        {"final_text", "launch_ts", "wall_s", "tokens": {...}, "offered_tools": [...], "attempts": [tool names the
         model called, as it named them], "error": str|None, "model": str}

The tools' calls themselves are written to `trace_path` (JSONL) by the stub (stub_pm.py), in another process for
`claude-code`, in this one for `openai-compatible`; `choice` writes one synthetic call. A rate limit raises
RateLimited so the run can stop and report.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

import stub_pm

HERE = os.path.dirname(os.path.abspath(__file__))
ACTION_TOOLS = {"start": "pm_worker_start", "message": "pm_worker_message", "stop": "pm_worker_stop",
                "decision": "pm_decision_open", "ask": "desktop_ask", "answer": "desktop_say"}


class RateLimited(Exception):
    pass


def tokens(inp=0, out=0, cache_read=0, cache_write=0, cost=0.0, turns=0) -> dict:
    return {"input": inp, "output": out, "cache_read": cache_read, "cache_write": cache_write,
            "total_input": inp + cache_read + cache_write, "cost_usd": round(cost, 5), "turns": turns}


class Fake:
    """For tests: `script` maps a message to a list of (tool, arguments) calls, run against the real stub."""

    name = "fake"

    def __init__(self, script):
        self.script = script

    def run(self, text, portfolio, trace_path):
        t0 = time.time()
        stub = stub_pm.Stub(portfolio, trace_path)
        attempts = []
        for name, args in self.script(text):
            attempts.append(name)
            if name in stub_pm.NAMES:
                stub.call(name, args)
        return {"final_text": "", "launch_ts": t0, "wall_s": time.time() - t0, "tokens": tokens(turns=1),
                "offered_tools": list(stub_pm.NAMES), "attempts": attempts, "error": None, "model": "fake"}


def openai_tools():
    return [{"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["inputSchema"]}}
            for t in stub_pm.TOOLS]


def post(url, body, timeout=600):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise RateLimited(str(e))
        raise


# MetaSoar trials/handler-ladder/parse.py EMPTY_THINKING: Inkling's chat template with its thinking closed before it starts
# (no request switch stops its thinking: 401 of 450 replies ran out inside it).
EMPTY_THINKING = "<|message_model|><|content_thinking|><|end_message|><|message_model|><|content_text|>"


class OpenAICompatible:
    """A tool-calling loop over a llama.cpp server's /v1/chat/completions with the same tool schemas. `extra` is merged
    into the request (e.g. {"chat_template_kwargs": {"enable_thinking": false}}). `prefill` closes the model's thinking
    before it starts, by ending the messages with an assistant message of EMPTY_THINKING (llama.cpp continues it):
    "off", "on", or "auto" (plain first; when a turn comes back with no tool call and no text, as when the budget went
    on thinking, switch to the prefill for the rest of the run, sticky across scenarios). `mode_log` records the switch."""

    def __init__(self, url, model="local", prompt_file=None, extra=None, max_turns=10, timeout=900, name=None,
                 prefill="off", max_tokens=2048):
        self.name = name or f"openai-compatible:{model}"
        self.url, self.model, self.extra, self.max_turns, self.timeout = url.rstrip("/"), model, extra or {}, max_turns, timeout
        self.prefill, self.max_tokens, self.mode_log = prefill, max_tokens, []
        with open(prompt_file or os.path.join(HERE, "manager.md")) as f:
            self.prompt = f.read()

    def turn(self, msgs):
        pre = self.prefill == "on"
        body = {"model": self.model, "tools": openai_tools(), "temperature": 0, "max_tokens": self.max_tokens, **self.extra,
                "messages": msgs + ([{"role": "assistant", "content": EMPTY_THINKING}] if pre else [])}
        r = post(self.url + "/v1/chat/completions", body, self.timeout)
        m = r["choices"][0]["message"]
        if self.prefill == "auto" and not m.get("tool_calls") and not (m.get("content") or "").strip():
            self.prefill = "on"
            self.mode_log.append("switched to the empty-thinking prefill after an empty turn")
            return self.turn(msgs)
        return r

    def run(self, text, portfolio, trace_path):
        stub = stub_pm.Stub(portfolio, trace_path)
        msgs = [{"role": "system", "content": self.prompt}, {"role": "user", "content": text}]
        tok, attempts, final, error, t0 = tokens(), [], "", None, time.time()
        for _ in range(self.max_turns):
            r = self.turn(msgs)
            u = r.get("usage") or {}
            tok = tokens(tok["input"] + u.get("prompt_tokens", 0), tok["output"] + u.get("completion_tokens", 0),
                         turns=tok["turns"] + 1)
            m = r["choices"][0]["message"]
            msgs.append({k: v for k, v in m.items() if k in ("role", "content", "tool_calls") and v is not None})
            final = m.get("content") or final
            calls = m.get("tool_calls") or []
            if not calls:
                break
            for c in calls:
                fn = c["function"]
                try:
                    args = fn.get("arguments") or "{}"
                    args = json.loads(args) if isinstance(args, str) else args
                except ValueError:
                    args = {}
                attempts.append(fn["name"])
                res = stub.call(fn["name"], args)[0] if fn["name"] in stub_pm.NAMES else f"no such tool: {fn['name']}"
                msgs.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": res})
        else:
            error = f"no final answer in {self.max_turns} turns"
        return {"final_text": final, "launch_ts": t0, "wall_s": time.time() - t0, "tokens": tok,
                "offered_tools": list(stub_pm.NAMES), "attempts": attempts, "error": error, "model": self.model,
                "prefill": self.prefill}


class Choice:
    """d1-2B's /v1/systemone for the routing decision only (MetaSoar trials/handler-ladder/stream_v3.py choose_d1):
    two choice questions, the project and the action. One synthetic call is written to the trace so the scorer treats
    it as any other arm; it has no brief, so brief quality is not scored."""

    def __init__(self, url="http://127.0.0.1:8083"):
        self.name = "choice:d1"
        self.url = url.rstrip("/")

    def ask(self, question, crit, instructions):
        d = post(self.url + "/v1/systemone", {"state": {"question": question}, "questions": {"q": {
            "type": "choice", "instructions": instructions, "criteria": crit}}}, 600)
        p = d["answers"]["q"]["probabilities"]
        return max(p, key=p.get)

    def run(self, text, portfolio, trace_path):
        t0 = time.time()
        stub = stub_pm.Stub(portfolio, trace_path)
        projects = {p["id"]: f"{p['goal']} (next: {p.get('next_step', '')})" for p in portfolio["projects"]}
        workers = "; ".join(f"{w['id']} on {w['project']}: {w['brief']}" for w in portfolio["workers"]) or "none"
        pj = self.ask(text, {**projects, "none": "no one project, or several, or a new one"},
                      f"Which project does this message concern? Running workers: {workers}.")
        acts = {"start": "start a new worker for the work asked",
                "message": "send an instruction to a running worker that already owns this work",
                "stop": "stop a running worker", "answer": "answer from what is already known, no worker",
                "ask": "ask the person which was meant, because it is ambiguous",
                "decision": "open a decision only the person may make (merge, settings, spend, a client, a failure)",
                "ack": "nothing: a status report that needs nobody"}
        ac = self.ask(text, acts, "What should the manager do with this message?")
        project = None if pj == "none" else pj
        worker = next((w["id"] for w in portfolio["workers"] if w["project"] == project), None)
        args = {"start": {"project": project, "runner": "local", "objective": "-", "output": "-", "boundaries": "-", "done_when": "-"},
                "message": {"worker": worker, "text": "-"}, "stop": {"worker": worker},
                "decision": {"kind": "question", "text": "-", "project": project}, "ask": {"question": "-"},
                "answer": {"text": "-"}}.get(ac)
        if ac != "ack":
            stub.call(ACTION_TOOLS[ac], {k: v for k, v in args.items() if v})
            stub.log({"note": "choice", "_project": project})
        return {"final_text": "", "launch_ts": t0, "wall_s": time.time() - t0, "tokens": tokens(turns=2),
                "offered_tools": [], "attempts": [], "error": None, "model": "d1", "choice": {"project": pj, "action": ac}}
