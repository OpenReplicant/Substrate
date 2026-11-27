#!/usr/bin/env python3
"""PM-1a's manager tools, as an MCP server over stdio (docs/manager-agent.md, section 8), standard library only.

The tools are the manager's and nothing else: it reads a stub portfolio, writes a note, starts (message, stops) a
stubbed worker, opens a decision, asks the person, and replies. No tool edits a file or runs a command; a start
records the call and returns a worker id. Every call is appended, with its arguments, to the JSONL trace.

    python3 -I stub_pm.py --portfolio portfolio.json --trace trace.jsonl

`Stub` is the same logic without the transport, for drivers that call tools in-process (openai-compatible) and for
the tests. MCP's stdio transport is JSON-RPC 2.0, one message per line.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import time

SERVER = "pm"
RUNNERS = ["local", "kaggle", "container"]

TOOLS = [
    {"name": "pm_portfolio",
     "description": "Read the portfolio: every project with its class, repo, goal, status, next step, judge, recent pull "
                    "requests and notes, the running workers, the open decisions, and the day's token meter. Pass "
                    "project to read one project.",
     "inputSchema": {"type": "object", "properties": {"project": {"type": "string", "description": "a project id"}}}},
    {"name": "kernel_search",
     "description": "Search the knowledge kernel's recorded decisions and notes (what was decided, and why).",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "project": {"type": "string"}},
                     "required": ["query"]}},
    {"name": "pm_project_note",
     "description": "Record a note on a project (its next step or a fact the portfolio should keep).",
     "inputSchema": {"type": "object", "properties": {"project": {"type": "string"}, "note": {"type": "string"},
                                                       "next_step": {"type": "string", "description": "replace the project's next step"}},
                     "required": ["project", "note"]}},
    {"name": "pm_worker_start",
     "description": "Start a worker on a project. Returns its id. The worker sees only this brief and its repository, so "
                    "the brief must settle everything it would otherwise have to ask.",
     "inputSchema": {"type": "object", "properties": {
         "project": {"type": "string", "description": "a project id"},
         "runner": {"type": "string", "enum": RUNNERS, "description": "where it runs"},
         "kind": {"type": "string", "enum": ["work", "judge"], "description": "judge: verify a finished worker's branch"},
         "objective": {"type": "string", "description": "what to achieve and why"},
         "output": {"type": "string", "description": "what it hands back (branch, pull request, results file)"},
         "boundaries": {"type": "string", "description": "what it must not do or touch"},
         "done_when": {"type": "string", "description": "the check that says it is finished"},
         "context": {"type": "string", "description": "facts from the portfolio or the conversation it needs"}},
         "required": ["project", "runner", "objective", "output", "boundaries", "done_when"]}},
    {"name": "pm_worker_message",
     "description": "Send a message to a running worker (an instruction, an answer, a changed plan).",
     "inputSchema": {"type": "object", "properties": {"worker": {"type": "string"}, "text": {"type": "string"}},
                     "required": ["worker", "text"]}},
    {"name": "pm_worker_stop",
     "description": "Stop a running worker.",
     "inputSchema": {"type": "object", "properties": {"worker": {"type": "string"}, "reason": {"type": "string"}},
                     "required": ["worker"]}},
    {"name": "pm_decision_open",
     "description": "Open a decision for the person: something only they may decide or must be told (a merge, a "
                    "setting, spend, client data, a failed worker). It waits in their inbox.",
     "inputSchema": {"type": "object", "properties": {
         "project": {"type": "string"}, "kind": {"type": "string", "enum": ["question", "review", "notify"]},
         "text": {"type": "string"}, "options": {"type": "array", "items": {"type": "string"}},
         "proposed": {"type": "string", "description": "the answer you would pick, when the facts settle it"}},
         "required": ["kind", "text"]}},
    {"name": "desktop_ask",
     "description": "Ask the person a question in the conversation, because the request is ambiguous. Waits for their answer.",
     "inputSchema": {"type": "object", "properties": {"question": {"type": "string"}, "options": {"type": "array", "items": {"type": "string"}}},
                     "required": ["question"]}},
    {"name": "desktop_say",
     "description": "Reply to the person in the conversation. Short: a few lines, no code.",
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
]
NAMES = [t["name"] for t in TOOLS]


class Stub:
    """A fresh portfolio and a trace. `call` returns (text, is_error)."""

    def __init__(self, portfolio: dict, trace_path: str | None = None):
        self.p = copy.deepcopy(portfolio)
        self.trace_path = trace_path
        self.n_workers = max([int(w["id"].split("-")[1]) for w in self.p.get("workers", []) if "-" in w["id"]] + [30])
        self.seq = 0

    def log(self, rec: dict) -> None:
        self.seq += 1
        rec = {"seq": self.seq, "ts": round(time.time(), 3), **rec}
        if self.trace_path:
            with open(self.trace_path, "a") as f:
                f.write(json.dumps(rec) + "\n")

    def project(self, pid):
        return next((x for x in self.p["projects"] if x["id"] == pid), None)

    def worker(self, wid):
        return next((w for w in self.p.get("workers", []) if w["id"] == wid), None)

    def call(self, name: str, args: dict) -> tuple[str, bool]:
        args = args if isinstance(args, dict) else {}
        text, err = self._call(name, args)
        self.log({"tool": name, "arguments": args, "error": err, "result": text[:300]})
        return text, err

    def _call(self, name, a):
        spec = next((t for t in TOOLS if t["name"] == name), None)
        if spec is None:
            return f"no such tool: {name}", True
        missing = [k for k in spec["inputSchema"].get("required", []) if a.get(k) in (None, "", [])]
        if missing:
            return f"missing required argument(s): {', '.join(missing)}", True
        if "project" in a and a["project"] and self.project(a["project"]) is None:
            return f"unknown project {a['project']!r}; projects: {', '.join(x['id'] for x in self.p['projects'])}", True
        if name == "pm_portfolio":
            if a.get("project"):
                pid = a["project"]
                return json.dumps({"project": self.project(pid), "workers": [w for w in self.p["workers"] if w["project"] == pid],
                                   "decisions": [d for d in self.p["decisions"] if d.get("project") == pid]}), False
            return json.dumps(self.p), False
        if name == "kernel_search":
            q = set(a["query"].lower().split())
            hits = [k for k in self.p.get("knowledge", []) if (not a.get("project") or k.get("project") == a["project"])
                    and q & set(k["text"].lower().replace(",", " ").replace(".", " ").split())]
            return json.dumps(hits or []), False
        if name == "pm_project_note":
            pr = self.project(a["project"])
            pr.setdefault("notes", []).append(a["note"])
            if a.get("next_step"):
                pr["next_step"] = a["next_step"]
            return "noted", False
        if name == "pm_worker_start":
            if a.get("runner") not in RUNNERS:
                return f"runner must be one of {RUNNERS}", True
            self.n_workers += 1
            wid = f"w-{self.n_workers}"
            self.p["workers"].append({"id": wid, "project": a["project"], "state": "starting", "brief": a["objective"]})
            return json.dumps({"worker": wid, "state": "starting"}), False
        if name in ("pm_worker_message", "pm_worker_stop"):
            w = self.worker(a["worker"])
            if w is None:
                return f"no such worker {a['worker']!r}; running: {', '.join(x['id'] for x in self.p['workers'])}", True
            if name == "pm_worker_stop":
                w["state"] = "stopped"
            return "sent" if name == "pm_worker_message" else "stopped", False
        if name == "pm_decision_open":
            did = f"d-{len(self.p['decisions']) + 1}"
            self.p["decisions"].append({"id": did, **{k: v for k, v in a.items() if v}})
            return json.dumps({"decision": did, "state": "open"}), False
        if name in ("desktop_ask", "desktop_say"):
            return "delivered" if name == "desktop_say" else "asked; the answer will arrive as the person's next message", False
        return "unreachable", True


def serve(stub: Stub, rd=sys.stdin, wr=sys.stdout) -> None:
    def reply(i, result=None, error=None):
        msg = {"jsonrpc": "2.0", "id": i}
        msg.update({"error": error} if error else {"result": result})
        wr.write(json.dumps(msg) + "\n")
        wr.flush()

    for line in rd:
        try:
            m = json.loads(line)
        except ValueError:
            continue
        method, i = m.get("method"), m.get("id")
        if i is None:
            continue
        if method == "initialize":
            reply(i, {"protocolVersion": (m.get("params") or {}).get("protocolVersion", "2025-06-18"),
                      "capabilities": {"tools": {}}, "serverInfo": {"name": SERVER, "version": "0.1"}})
        elif method == "tools/list":
            reply(i, {"tools": TOOLS})
        elif method == "tools/call":
            p = m.get("params") or {}
            text, err = stub.call(p.get("name", ""), p.get("arguments") or {})
            reply(i, {"content": [{"type": "text", "text": text}], "isError": err})
        elif method == "ping":
            reply(i, {})
        else:
            reply(i, error={"code": -32601, "message": f"no such method {method}"})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--portfolio", required=True)
    ap.add_argument("--trace", required=True)
    a = ap.parse_args()
    with open(a.portfolio) as f:
        serve(Stub(json.load(f), a.trace))


if __name__ == "__main__":
    main()
