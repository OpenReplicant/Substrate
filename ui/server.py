"""The UI's server (plan step 3b; S-140): the store's pages and maps, read-only, on the standard library.

    python3 -m ui.server                     # 127.0.0.1:UI_PORT (8100); the database is STORE_URL, libpq's PG* or .env's

The entities, search, pages and maps come from the Knowledge Kernel's `substrate` schema (modules/view-substrate in
the kernel's repository; S-153, S-154), in the database KERNEL_URL names (default: database `kernel` in the same
Postgres, as the kernel's own login), read as the module's role kkm_view_substrate so the kernel's row-level security
applies. The companion's conversation (the `env` schema) is on STORE_URL. Entity ids are the Q numbers Substrate's
store gave: urn:kk:substrate:Q10 in the kernel, Q10 here.

In the stack it is the compose service `ui` (deploy/compose.yaml), published on 127.0.0.1:UI_PORT.

  GET /                         the page (ui/static/index.html); routes are in its hash: #/map/Q10, #/e/Q10
  GET /static/...               ui/static
  GET /api/search?q=...         entities by label, alias, key or page words
  GET /api/wholes               entities with parts: what has a map
  GET /api/entity/Q10           label, description, the page (substrate.page) and whether it has a map
  GET /api/map/Q10[?depth=6]    nodes (id, label, description, kind) and edges (source, target, kind, statement,
                                flagged): substrate.map_nodes and substrate.map (statement: the claim's id)

  GET  /api/companion            the companion's conversation (the owner's messages, its replies, its tasks and
                                proposals, in order), the proposals waiting, the latest meter, its budget and model
  GET  /api/worker               the worker's log (what the owner asked, its results with calls and cited claim ids, its
                                 hand-offs waiting for the owner)
  POST /api/worker/say          {"text"}: a task for the worker (env.publish worker.owner.message)
  POST /api/worker/decide       {"action", "approve", "reason"}: the owner decides a hand-off to the companion
  POST /api/companion/say       {"text"}: the owner says something (env.publish companion.owner.message)
  POST /api/companion/decide    {"action", "approve", "reason"}: the owner decides a proposal (env.decide)
  POST /api/companion/improve   {"why"}: the owner asks for a new version of the voice reply component (S-151)

Every response carries the UI's Content-Security-Policy (deploy/caddy/Caddyfile's, without frames): scripts and
styles only from this origin. Reads are on a read-only session; the store's writes go through the agent's tools
(the kernel's MCP server, profile substrate). The two POSTs are the owner's, as OWNER_NAME: they are accepted only
as JSON from this origin (Origin, and Sec-Fetch-Site when the browser sends it), so another page cannot speak or
decide for the owner.
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
from urllib.parse import parse_qs, quote, urlparse

import psycopg
import psycopg.sql

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
    from environment.db import database_url as from_env
    return from_env()


NS = "urn:kk:substrate:"            # an item of Substrate's store, as an IRI in the kernel
WDT = "http://www.wikidata.org/prop/direct/"
KERNEL_ROLE = os.environ.get("KERNEL_ROLE") or "kkm_view_substrate"


def kernel_url() -> str:
    """The kernel's database: KERNEL_URL, else the `kernel` database beside the store's (libpq's PG* in a container,
    else .env's: the kernel's own login kk_authenticator, which may switch to the read model's role)."""
    if os.environ.get("KERNEL_URL"):
        return os.environ["KERNEL_URL"]
    if os.environ.get("PGHOST"):
        db, pw = os.environ.get("KERNEL_DB") or "kernel", os.environ.get("KK_AUTHENTICATOR_PASSWORD")
        if pw:                                            # the stack's container: the kernel's login on the same host
            return f"postgresql://kk_authenticator:{quote(pw, safe='')}@{os.environ['PGHOST']}:{os.environ.get('PGPORT') or 5432}/{db}"
        return "dbname=" + db
    sys.path[:0] = [str(ROOT / "scripts"), str(ROOT)]
    from db import kernel_url as from_env
    from gateway import settings
    return from_env(settings())


class Store:
    """One connection, used by one request at a time: read-only, or (write=True) for the owner's two writes. With a
    role, every session switches to it first (the kernel's read model runs as its own role)."""

    def __init__(self, url: str, write: bool = False, role: str | None = None):
        self.url, self.lock, self.conn, self.role = url, threading.Lock(), None, role
        self.options = "-c statement_timeout=10000" + ("" if write else " -c default_transaction_read_only=on")

    def query(self, sql: str, args=()) -> list[tuple]:
        with self.lock:
            for attempt in (1, 2):                       # reconnect once if Postgres restarted under us
                try:
                    if self.conn is None or self.conn.closed:
                        self.conn = psycopg.connect(self.url, autocommit=True, options=self.options)
                        if self.role:
                            self.conn.execute(psycopg.sql.SQL("set role {}").format(psycopg.sql.Identifier(self.role)))
                    return self.conn.execute(sql, args).fetchall()
                except psycopg.OperationalError:
                    self.conn = None
                    if attempt == 2:
                        raise


def api(store: Store, path: str, q: dict, kernel: Store) -> tuple[int, object]:
    """store: Substrate's database (the `env` schema); kernel: the kernel's read model."""
    parts = path.strip("/").split("/")[1:]            # after "api"
    if parts == ["companion"]:
        return 200, companion(store)
    if parts == ["worker"]:
        return 200, worker(store)
    return from_kernel(kernel, parts, q)


def to_iri(eid: str) -> str:
    return WDT + eid if eid.startswith("P") else NS + eid


def to_id(iri: str) -> str:
    return iri.removeprefix(NS)


def from_kernel(k: Store, parts: list[str], q: dict) -> tuple[int, object]:
    if parts == ["search"]:
        text = (q.get("q") or [""])[0].strip()
        if not text:
            return 200, []
        rows = k.query("select id, label, description from substrate.search(%s, %s)", (text, 20))
        return 200, [{"id": i, "label": la, "description": d} for i, la, d in rows if ENTITY.match(i)]
    if parts == ["wholes"]:
        rows = k.query("select id, label, description, parts from substrate.wholes limit 200")
        return 200, [{"id": i, "label": la, "description": d, "parts": n} for i, la, d, n in rows if ENTITY.match(i)]
    if len(parts) == 2 and parts[0] in ("entity", "map") and ENTITY.match(parts[1]):
        eid, iri = parts[1], to_iri(parts[1])
        md = k.query("select substrate.page(%s)", (iri,))[0][0]
        row = k.query("select label, description from substrate.entity where iri = %s", (iri,))
        if md is None and not row:
            return 404, {"error": f"no entity {eid}"}
        label, description = row[0] if row else (k.query("select substrate.label(%s)", (iri,))[0][0], None)
        if parts[0] == "entity":
            has_map = bool(k.query("select 1 from substrate.wholes where iri = %s", (iri,)))
            return 200, {"id": eid, "label": label, "description": description, "markdown": md, "has_map": has_map}
        depth = max(1, min(int((q.get("depth") or ["6"])[0]), 12))
        nodes = k.query("select id, label, description, kind from substrate.map_nodes(%s, %s)", (iri, depth))
        edges = k.query("select source, target, kind, statement, flagged from substrate.map(%s, %s)", (iri, depth))
        return 200, {"whole": eid, "label": label,
                     "nodes": [{"id": to_id(i), "label": la, "description": d, "kind": kd} for i, la, d, kd in nodes],
                     "edges": [{"source": to_id(s), "target": to_id(t), "kind": kd, "statement": str(st) if st else None,
                                "flagged": f} for s, t, kd, st, f in edges]}
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


# The worker's page (plan step 1, S-163): what the owner asked, what it did (with its model calls, the calls a compiled
# skill saved and the claims it cited), and its hand-offs to the companion that wait for the owner
WORKER_LOG = """
select * from (
  select 'said' as kind, s.at, s.source as who, s.body as body, null::bigint as action, null as status
    from env.signal s where s.key in ('worker.owner.message', 'worker.task')
  union all
  select 'done', s.at, s.source, s.body, null, case when (s.body->>'ok')::boolean then 'applied' else 'failed' end
    from env.signal s where s.key = 'worker.task.done'
  union all
  select 'proposal', a.at, a.caller, a.input, a.id, a.status from env.action a where a.actuator = 'worker.ask_companion'
) w order by at desc limit %s
"""


def worker(store: Store, limit: int = 100) -> dict:
    rows = store.query(WORKER_LOG, (limit,))
    log = [{"kind": k, "at": at.isoformat(), "who": who, "action": a, "status": st,
            "text": (b or {}).get("text"), "task": (b or {}).get("task"), "model_calls": (b or {}).get("model_calls"),
            "skipped_calls": (b or {}).get("skipped_calls"), "cited": (b or {}).get("cited") or []}
           for k, at, who, b, a, st in reversed(rows)]
    waiting = store.query("select id, input, caller, at from env.action where actuator = 'worker.ask_companion' "
                          "and status = 'proposed' order by id")
    return {"owner": OWNER, "log": log,
            "waiting": [{"action": i, "input": inp, "by": c, "at": at.isoformat()} for i, inp, c, at in waiting]}


def post(writer: Store, path: str, body: dict) -> tuple[int, object]:
    if path == "/api/worker/say":
        text = body.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > 20000:
            return 400, {"error": "say needs text (at most 20000 characters)"}
        sid = writer.query("select env.publish('worker.owner.message', %s::jsonb, %s)",
                           (json.dumps({"text": text.strip()}), OWNER))[0][0]
        return 200, {"signal": sid}
    if path == "/api/worker/decide":
        action, approve, reason = body.get("action"), body.get("approve"), body.get("reason")
        if not isinstance(action, int) or not isinstance(approve, bool) or not (reason is None or isinstance(reason, str)):
            return 400, {"error": "decide needs action (a number) and approve (true or false), and may give a reason"}
        if not writer.query("select 1 from env.action where id = %s and actuator = 'worker.ask_companion'", (action,)):
            return 404, {"error": f"no worker hand-off {action}"}
        status = writer.query("select env.decide(%s, %s, %s, %s)", (action, approve, OWNER, reason or None))[0][0]
        return 200, {"action": action, "status": status}
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


def handler(store: Store, writer: Store, kernel: Store):
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
                    status, obj = api(store, u.path, parse_qs(u.query), kernel)
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
                status, obj = post(writer, u.path, body if isinstance(body, dict) else {})
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


def serve(host: str, port: int, url: str, kernel: str) -> ThreadingHTTPServer:
    """url: Substrate's database (the `env` schema); kernel: the kernel's, for the entities, pages and maps."""
    return ThreadingHTTPServer((host, port), handler(Store(url), Store(url, write=True), Store(kernel, role=KERNEL_ROLE)))


def main():
    host = os.environ.get("UI_HOST", "127.0.0.1")
    port = int(os.environ.get("UI_PORT") or 8100)
    srv = serve(host, port, database_url(), kernel_url())
    print(f"the UI on http://{host}:{port}/", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
