"""The desktop's server (S-206; the product cut's step 2): the conversation between a person and the agents, as signals in
the environment (environment/sql/011_desktop.sql), with two faces.

  POST /mcp          MCP over streamable HTTP (stateless, JSON answers) for the MCP router, which reaches it through its
                     connector, each call signed as its caller (S-205). Tools, each recorded and gated by the router:
                       say(text, to)              an agent says something to a person (or `all`)
                       show(kind, id, title, to)  an agent puts something in front of them: a view, an app or a claim
                       ask(question, to)          an agent asks; the person answers in the chat
                       feed(person, after)        the conversation, for an agent that does not listen on the channel
  GET  /api/feed     the signed-in person's conversation after an id, waiting up to `wait` seconds for something new
  POST /api/post     the person says something: {text, reply_to?}; a signal desktop.<person>.message, which the
                     assistant hears on its channel (environment/channel.py, pattern desktop.*.message)
  GET  /healthz

Everything takes the kernel's token (HS256, a `role` claim; KK_JWT_SECRET). The chat window reads and posts here, not
through the router: a person's reading is not an action, and their messages are signals, recorded whole already.
Standard library and psycopg only (the tools image). Env: DATABASE_URL (the desktop's login), KK_JWT_SECRET, PORT.

    python3 -m desktop.server
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import psycopg

SECRET = os.environ.get("KK_JWT_SECRET", "")
DB = os.environ.get("DATABASE_URL", "")
VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26")
WHO = re.compile(r"^(person_[a-z0-9_]+|all)$")
KINDS = ("view", "app", "claim")
HEADERS = {"Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'", "X-Content-Type-Options": "nosniff",
           "Referrer-Policy": "no-referrer", "Cache-Control": "no-store"}


def role_of(auth: str) -> str | None:
    """The caller's role from a kernel token: HS256 only, signature in constant time, exp and role required."""
    if not SECRET or not auth.startswith("Bearer "):
        return None
    parts = auth[7:].strip().split(".")
    if len(parts) != 3:
        return None
    pad = lambda s: s + "=" * (-len(s) % 4)
    try:
        head = json.loads(base64.urlsafe_b64decode(pad(parts[0])))
        sig = base64.urlsafe_b64decode(pad(parts[2]))
        body = json.loads(base64.urlsafe_b64decode(pad(parts[1])))
    except (ValueError, TypeError):
        return None
    want = hmac.new(SECRET.encode(), f"{parts[0]}.{parts[1]}".encode(), hashlib.sha256).digest()
    if head.get("alg") != "HS256" or not hmac.compare_digest(sig, want):
        return None
    if not body.get("role") or not body.get("exp") or time.time() >= body["exp"]:
        return None
    return str(body["role"])


def publish(key: str, body: dict, by: str) -> int:
    with psycopg.connect(DB, autocommit=True) as c:
        return c.execute("select env.publish(%s, %s::jsonb, %s)", (key, json.dumps(body), by)).fetchone()[0]


def feed(person: str, after: int, limit: int = 100, wait: float = 0) -> list[dict]:
    until = time.time() + max(0.0, min(wait, 25.0))
    with psycopg.connect(DB, autocommit=True) as c:
        while True:
            rows = c.execute("select id, to_, kind, body, source, at from env.desktop_feed(%s, %s, %s)",
                             (person, after, limit)).fetchall()
            if rows or time.time() >= until:
                return [{"id": i, "to": t, "kind": k, "body": b, "by": s, "at": a.isoformat()} for i, t, k, b, s, a in rows]
            time.sleep(0.5)


def tool(name, description, props, required, read_only=False):
    return {"name": name, "description": description,
            "inputSchema": {"type": "object", "properties": props, "required": required},
            "annotations": {"readOnlyHint": read_only, "destructiveHint": False, "openWorldHint": False}}


TO = {"type": "string", "description": "a person's role (person_owner) or `all`", "default": "all"}
TOOLS = [
    tool("say", "Say something to a person in the desktop's chat (or to everyone signed in).",
         {"text": {"type": "string"}, "to": TO}, ["text"]),
    tool("show", "Put something in front of a person in the desktop: a view (its launcher id, e.g. view:view-map), an "
         "app (app:maps) or a claim (its id); it appears in the chat with a button that opens it.",
         {"kind": {"type": "string", "enum": list(KINDS)}, "id": {"type": "string"}, "title": {"type": "string"}, "to": TO},
         ["kind", "id"]),
    tool("ask", "Ask a person a question in the desktop's chat; their answer arrives as a desktop message replying to it.",
         {"question": {"type": "string"}, "to": TO}, ["question"]),
    tool("feed", "The desktop conversation with a person after an id: their messages, and what was said, shown or asked.",
         {"person": {"type": "string"}, "after": {"type": "integer", "default": 0}}, ["person"], read_only=True),
]


def call(name: str, args: dict, caller: str) -> dict:
    """A tool call; returns an MCP CallToolResult."""
    text = lambda t, err=False: {"content": [{"type": "text", "text": t}], "isError": err}
    to = str(args.get("to") or "all")
    if name in ("say", "show", "ask") and not WHO.match(to):
        return text(f"`to` is a person's role (person_<name>) or `all`, not {to!r}", True)
    if name == "say":
        if not str(args.get("text", "")).strip():
            return text("say needs text", True)
        return text(f"said (signal {publish(f'desktop.{to}.reply', {'text': str(args['text'])}, caller)})")
    if name == "show":
        if args.get("kind") not in KINDS or not str(args.get("id", "")).strip():
            return text(f"show needs kind ({', '.join(KINDS)}) and id", True)
        sid = publish(f"desktop.{to}.show", {"kind": args["kind"], "id": str(args["id"]),
                                             "title": str(args.get("title") or args["id"])}, caller)
        return text(f"shown (signal {sid})")
    if name == "ask":
        if not str(args.get("question", "")).strip():
            return text("ask needs a question", True)
        sid = publish(f"desktop.{to}.ask", {"question": str(args["question"])}, caller)
        return text(f"asked (signal {sid}); the answer arrives as a desktop.{to if to != 'all' else '<person>'}.message "
                    f"with reply_to {sid}")
    if name == "feed":
        person = caller if caller.startswith("person_") else str(args.get("person") or "")
        if not WHO.match(person) or person == "all":
            return text("feed needs a person (person_<name>)", True)
        rows = feed(person, int(args.get("after") or 0))
        return {"content": [{"type": "text", "text": json.dumps(rows)}], "structuredContent": {"messages": rows},
                "isError": False}
    return text(f"no tool {name}", True)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *a):
        sys.stderr.write("desktop: " + (fmt % a) + "\n")

    def send(self, code: int, body=None, ctype="application/json"):
        data = b"" if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
        self.send_response(code)
        for k, v in HEADERS.items():
            self.send_header(k, v)
        if data:
            self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return {}

    def do_GET(self):
        u = urlsplit(self.path)
        if u.path == "/healthz":
            return self.send(200, b"ok", "text/plain")
        if u.path == "/mcp":
            return self.send(405)                       # no server-sent stream: every answer comes with its request
        if u.path == "/api/feed":
            who = role_of(self.headers.get("Authorization", ""))
            if not who or not who.startswith("person_"):
                return self.send(401, {"error": "sign in as a person"})
            q = parse_qs(u.query)
            after = int((q.get("after") or ["0"])[0] or 0)
            wait = float((q.get("wait") or ["0"])[0] or 0)
            return self.send(200, feed(who, after, 200, wait))
        self.send(404, {"error": "not found"})

    def do_POST(self):
        u = urlsplit(self.path)
        who = role_of(self.headers.get("Authorization", ""))
        if u.path == "/api/post":
            if not who or not who.startswith("person_"):
                return self.send(401, {"error": "sign in as a person"})
            b = self.body()
            text = str(b.get("text", "")).strip()
            if not text:
                return self.send(400, {"error": "send {text}"})
            msg = {"text": text[:8000], **({"reply_to": int(b["reply_to"])} if str(b.get("reply_to", "")).isdigit() else {})}
            return self.send(200, {"id": publish(f"desktop.{who}.message", msg, who)})
        if u.path != "/mcp":
            return self.send(404, {"error": "not found"})
        if not who:
            return self.send(401, {"jsonrpc": "2.0", "id": None, "error": {"code": -32001, "message": "no valid token"}})
        m = self.body()
        if "id" not in m:                                   # a notification (initialized, cancelled): nothing to answer
            return self.send(202)
        meth, p = m.get("method"), m.get("params") or {}
        try:
            if meth == "initialize":
                v = p.get("protocolVersion")
                r = {"protocolVersion": v if v in VERSIONS else VERSIONS[0], "capabilities": {"tools": {}},
                     "serverInfo": {"name": "substrate-desktop", "version": "0.1.0"},
                     "instructions": "The desktop's chat with the people signed in to it (S-206)."}
            elif meth == "tools/list":
                r = {"tools": TOOLS}
            elif meth == "tools/call":
                r = call(str(p.get("name")), p.get("arguments") or {}, who)
            elif meth == "ping":
                r = {}
            else:
                return self.send(200, {"jsonrpc": "2.0", "id": m["id"], "error": {"code": -32601, "message": "method not found"}})
        except psycopg.Error as e:
            r = {"content": [{"type": "text", "text": f"the environment refused: {e.diag.message_primary or e}"}], "isError": True}
        self.send(200, {"jsonrpc": "2.0", "id": m["id"], "result": r})


def main():
    if len(SECRET) < 32 or not DB:
        sys.exit("desktop: KK_JWT_SECRET (32+ characters) and DATABASE_URL are needed")
    port = int(os.environ.get("PORT", "8095"))
    print(f"desktop: listening on :{port}", file=sys.stderr, flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
