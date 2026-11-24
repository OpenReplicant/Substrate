"""The trial's stand-in for the review lane (S-204): a router asks it, per tool call, whether the call may go. It allows
any tool whose name is not in HOLD; a held tool is refused until a person approves it (POST /approve {"tool": NAME}),
and every question is logged, so the trial can see that the router asked, with whose identity and which tool.
Standard library only.

  GET  /log                 what was asked
  POST /approve {tool}      approve the next calls of that tool
  POST /decide  (any JSON)  the router's question; answers {"decision": true|false, "reason": ...}
"""
import json, os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOLD = set(os.environ.get("HOLD", "write_note").split(","))
approved, log = set(), []


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, code, body):
        b = json.dumps(body).encode()
        self.send_response(code); self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        self.reply(200, log) if self.path == "/log" else self.reply(404, {})

    def do_POST(self):
        n = int(self.headers.get("content-length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/approve":
            approved.add(body.get("tool")); return self.reply(200, {"approved": sorted(approved)})
        tool = (body.get("resource") or {}).get("id") or body.get("tool")
        ok = tool not in HOLD or tool in approved
        log.append({"tool": tool, "subject": body.get("subject"), "decision": ok,
                    "headers": {k: v for k, v in self.headers.items() if k.lower().startswith("x-")}})
        self.reply(200, {"decision": ok, "reason": "allowed" if ok else f"{tool} waits for a person's approval"})


ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "9090"))), H).serve_forever()
