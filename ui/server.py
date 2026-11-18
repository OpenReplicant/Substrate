"""The UI's server (plan step 3b; S-140): the store's pages and maps, read-only, on the standard library.

    python3 -m ui.server                     # 127.0.0.1:UI_PORT (8100); the database is STORE_URL, libpq's PG* or .env's

In the stack it is the compose service `ui` (deploy/compose.yaml), published on 127.0.0.1:UI_PORT.

  GET /                         the page (ui/static/index.html); routes are in its hash: #/map/Q10, #/e/Q10
  GET /static/...               ui/static
  GET /api/search?q=...         entities by label, alias, key or page words
  GET /api/wholes               entities with parts: what has a map
  GET /api/entity/Q10           label, description, the page (store.render) and whether it has a map
  GET /api/map/Q10[?depth=6]    nodes (id, label, description, kind) and edges (source, target, kind, statement,
                                flagged): store.map_nodes and store.map

  GET  /api/companion            the companion's conversation (the owner's messages, its replies, its tasks and
                                proposals, in order), the proposals waiting, the latest meter, its budget and model
  POST /api/companion/say       {"text"}: the owner says something (env.publish companion.owner.message)
  POST /api/companion/decide    {"action", "approve", "reason"}: the owner decides a proposal (env.decide)
  POST /api/companion/improve   {"why"}: the owner asks for a new version of the voice reply component (S-151)

Every response carries the UI's Content-Security-Policy (deploy/caddy/Caddyfile's, without frames): scripts and
styles only from this origin. Reads are on a read-only session; the store's writes go through the agent's tools
(store/mcp.py). The two POSTs are the owner's, as OWNER_NAME: they are accepted only as JSON from this origin
(Origin, and Sec-Fetch-Site when the browser sends it), so another page cannot speak or decide for the owner.
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import psycopg

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "ui" / "static"
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
       "frame-ancestors 'none'; object-src 'none'; base-uri 'none'; form-action 'self'")
ENTITY = re.compile(r"^[QP][1-9][0-9]*$")


def database_url() -> str:
    if os.environ.get("STORE_URL"):
        return os.environ["STORE_URL"]
    if os.environ.get("PGHOST"):                          # in its container: libpq's PGHOST, PGUSER, PGPASSWORD, PGDATABASE
        return ""
    sys.path[:0] = [str(ROOT / "scripts"), str(ROOT)]
    from store.mcp import database_url as from_env
    return from_env()


class Store:
    """One connection, used by one request at a time: read-only, or (write=True) for the owner's two writes."""

    def __init__(self, url: str, write: bool = False):
        self.url, self.lock, self.conn = url, threading.Lock(), None
        self.options = "-c statement_timeout=10000" + ("" if write else " -c default_transaction_read_only=on")

    def query(self, sql: str, args=()) -> list[tuple]:
        with self.lock:
            for attempt in (1, 2):                       # reconnect once if Postgres restarted under us
                try:
                    if self.conn is None or self.conn.closed:
                        self.conn = psycopg.connect(self.url, autocommit=True, options=self.options)
                    return self.conn.execute(sql, args).fetchall()
                except psycopg.OperationalError:
                    self.conn = None
                    if attempt == 2:
                        raise


def api(store: Store, path: str, q: dict) -> tuple[int, object]:
    parts = path.strip("/").split("/")[1:]            # after "api"
    if parts == ["search"]:
        text = (q.get("q") or [""])[0].strip()
        if not text:
            return 200, []
        rows = store.query("select id, label, description from store.search(%s, %s)", (text, 20))
        return 200, [{"id": i, "label": la, "description": d} for i, la, d in rows]
    if parts == ["wholes"]:
        rows = store.query(
            "select e.id, e.label, e.description, count(*) from store.usable u join store.entity e on e.id = u.subject "
            "where u.property = store.key('has-part') group by e.id order by count(*) desc, e.label limit 200")
        return 200, [{"id": i, "label": la, "description": d, "parts": n} for i, la, d, n in rows]
    if len(parts) == 2 and parts[0] in ("entity", "map") and ENTITY.match(parts[1]):
        eid = parts[1]
        row = store.query("select label, description from store.entity where id = %s", (eid,))
        if not row:
            return 404, {"error": f"no entity {eid}"}
        if parts[0] == "entity":
            md = store.query("select store.render(%s)", (eid,))[0][0]
            has_map = bool(store.query("select 1 from store.usable where subject = %s and property = store.key('has-part') limit 1", (eid,)))
            return 200, {"id": eid, "label": row[0][0], "description": row[0][1], "markdown": md, "has_map": has_map}
        depth = max(1, min(int((q.get("depth") or ["6"])[0]), 12))
        nodes = store.query("select id, label, description, kind from store.map_nodes(%s, %s)", (eid, depth))
        edges = store.query("select source, target, kind, statement, flagged from store.map(%s, %s)", (eid, depth))
        return 200, {"whole": eid, "label": row[0][0],
                     "nodes": [{"id": i, "label": la, "description": d, "kind": k} for i, la, d, k in nodes],
                     "edges": [{"source": s, "target": t, "kind": k, "statement": str(st) if st else None, "flagged": f}
                               for s, t, k, st, f in edges]}
    if parts == ["companion"]:
        return 200, companion(store)
    return 404, {"error": "no such route"}


OWNER = os.environ.get("OWNER_NAME") or "owner"

# The companion's conversation: what the owner said, what it replied, the tasks it started and their results, its
# proposals and their decisions, each as it is in the record (env.signal, env.action)
CONVERSATION = """
select * from (
  select 'said' as kind, s.at, s.source as who, s.body->>'text' as text, null::bigint as action, null as status, s.id as ref
    from env.signal s where s.key = 'companion.owner.message'
  union all
  select case a.actuator when 'companion.reply' then 'reply' when 'companion.task' then 'task' else 'proposal' end,
         a.at, a.caller, coalesce(a.input->>'text', a.input->>'prompt', a.input::text), a.id, a.status, a.id
    from env.action a where a.actuator like 'companion.%%' and not (a.actuator = 'companion.reply' and a.status <> 'applied')
  union all
  select 'task_done', s.at, s.source, s.body->>'text', (s.body->>'action')::bigint,
         case when (s.body->>'ok')::boolean then 'applied' else 'failed' end, s.id
    from env.signal s where s.key = 'companion.task.done'
  union all
  select 'decided', a.decided_at, a.decided_by, a.reason, a.id, a.status, a.id
    from env.action a where a.actuator like 'companion.%%' and a.decided_at is not null
) c order by at desc limit %s
"""


def companion(store: Store, limit: int = 200) -> dict:
    rows = store.query(CONVERSATION, (limit,))
    convo = [{"kind": k, "at": at.isoformat(), "who": w, "text": t, "action": a, "status": st}
             for k, at, w, t, a, st, _ in reversed(rows)]
    waiting = store.query("select id, actuator, input, caller, at from env.action where actuator like 'companion.%%' "
                          "and status = 'proposed' order by id")
    meter = store.query("select body, at from env.signal where key = 'companion.meter.spend' order by id desc limit 1")
    gates = store.query("select name, gate, set_by from env.actuator where name like 'companion.%%' order by name")
    settings = store.query("select name, value, set_by, at from env.current where env = 'companion'")
    comps = store.query("select c.id, c.name, c.version, c.status, c.author, c.card->>'rationale', v.outcome, v.kpis "
                        "from env.component c left join env.verdict v on v.component = c.id "
                        "where c.env = 'companion' order by c.id desc limit 10")
    return {"owner": OWNER, "conversation": convo,
            "waiting": [{"action": i, "actuator": n, "input": inp, "by": c, "at": at.isoformat()} for i, n, inp, c, at in waiting],
            "meter": {**meter[0][0], "at": meter[0][1].isoformat()} if meter else None,
            "gates": {n: {"gate": g, "set_by": b} for n, g, b in gates},
            "settings": {n: {"value": v, "set_by": b, "at": at.isoformat()} for n, v, b, at in settings},
            "components": [{"id": i, "name": n, "version": v, "status": st, "author": au, "rationale": ra, "outcome": o, "kpis": k}
                           for i, n, v, st, au, ra, o, k in comps]}


def post(writer: Store, path: str, body: dict) -> tuple[int, object]:
    if path == "/api/companion/say":
        text = body.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > 20000:
            return 400, {"error": "say needs text (at most 20000 characters)"}
        sid = writer.query("select env.publish('companion.owner.message', %s::jsonb, %s)",
                           (json.dumps({"text": text.strip()}), OWNER))[0][0]
        return 200, {"signal": sid}
    if path == "/api/companion/improve":
        why = body.get("why")
        if not (why is None or isinstance(why, str)) or len(why or "") > 2000:
            return 400, {"error": "improve takes an optional reason (text)"}
        action, status = writer.query("select * from env.act('companion.improve', %s::jsonb, %s)",
                                      (json.dumps({"component": "voice_reply", "why": (why or "").strip() or None}), OWNER))[0]
        return 200, {"action": action, "status": status}
    if path == "/api/companion/decide":
        action, approve, reason = body.get("action"), body.get("approve"), body.get("reason")
        if not isinstance(action, int) or not isinstance(approve, bool) or not (reason is None or isinstance(reason, str)):
            return 400, {"error": "decide needs action (a number) and approve (true or false), and may give a reason"}
        if not writer.query("select 1 from env.action where id = %s and actuator like 'companion.%%'", (action,)):
            return 404, {"error": f"no companion action {action}"}
        status = writer.query("select env.decide(%s, %s, %s, %s)", (action, approve, OWNER, reason or None))[0][0]
        return 200, {"action": action, "status": status}
    return 404, {"error": "no such route"}


def handler(store: Store, writer: Store | None = None):
    class Handler(BaseHTTPRequestHandler):
        server_version = "substrate-ui"

        def send(self, status: int, body: bytes, ctype: str):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "same-origin")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def do_GET(self):
            u = urlparse(self.path)
            if u.path.startswith("/api/"):
                try:
                    status, obj = api(store, u.path, parse_qs(u.query))
                except (psycopg.Error, ValueError) as e:
                    status, obj = 500, {"error": type(e).__name__ + ": " + str(e).strip().splitlines()[0]}
                return self.send(status, json.dumps(obj, default=str).encode(), "application/json")
            rel = "index.html" if u.path in ("/", "/index.html") else u.path.removeprefix("/static/") if u.path.startswith("/static/") else None
            f = (STATIC / rel).resolve() if rel else None
            if not f or not f.is_file() or STATIC.resolve() not in f.parents:
                return self.send(404, b"not found", "text/plain")
            ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith("javascript"):
                ctype += "; charset=utf-8"
            self.send(200, f.read_bytes(), ctype)

        do_HEAD = do_GET

        def do_POST(self):
            u = urlparse(self.path)
            host = self.headers.get("Host") or ""
            origin = self.headers.get("Origin") or ""
            same = origin in (f"http://{host}", f"https://{host}") and self.headers.get("Sec-Fetch-Site", "same-origin") == "same-origin"
            if not same or not (self.headers.get("Content-Type") or "").startswith("application/json"):
                return self.send(403, b'{"error": "only JSON from this page"}', "application/json")
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(min(n, 100_000)) or b"{}")
                status, obj = post(writer or store, u.path, body if isinstance(body, dict) else {})
            except json.JSONDecodeError:
                status, obj = 400, {"error": "not JSON"}
            except (psycopg.Error, ValueError) as e:
                status, obj = 400 if isinstance(e, psycopg.errors.RaiseException) else 500, \
                    {"error": str(e).strip().splitlines()[0]}
            self.send(status, json.dumps(obj, default=str).encode(), "application/json")

        def log_message(self, fmt, *args):
            if os.environ.get("UI_LOG"):
                super().log_message(fmt, *args)

    return Handler


def serve(host: str, port: int, url: str) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(Store(url), Store(url, write=True)))


def main():
    host = os.environ.get("UI_HOST", "127.0.0.1")
    port = int(os.environ.get("UI_PORT") or 8100)
    srv = serve(host, port, database_url())
    print(f"the UI on http://{host}:{port}/", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
