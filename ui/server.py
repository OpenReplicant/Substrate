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

Every response carries the UI's Content-Security-Policy (deploy/caddy/Caddyfile's, without frames): scripts and
styles only from this origin. The session is read-only; writes go through the agent's tools (store/mcp.py).
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
    """One read-only connection, used by one request at a time."""

    def __init__(self, url: str):
        self.url, self.lock, self.conn = url, threading.Lock(), None

    def query(self, sql: str, args=()) -> list[tuple]:
        with self.lock:
            for attempt in (1, 2):                       # reconnect once if Postgres restarted under us
                try:
                    if self.conn is None or self.conn.closed:
                        self.conn = psycopg.connect(self.url, autocommit=True,
                                                    options="-c default_transaction_read_only=on -c statement_timeout=10000")
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
    return 404, {"error": "no such route"}


def handler(store: Store):
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
                return self.send(status, json.dumps(obj).encode(), "application/json")
            rel = "index.html" if u.path in ("/", "/index.html") else u.path.removeprefix("/static/") if u.path.startswith("/static/") else None
            f = (STATIC / rel).resolve() if rel else None
            if not f or not f.is_file() or STATIC.resolve() not in f.parents:
                return self.send(404, b"not found", "text/plain")
            ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith("javascript"):
                ctype += "; charset=utf-8"
            self.send(200, f.read_bytes(), ctype)

        do_HEAD = do_GET

        def log_message(self, fmt, *args):
            if os.environ.get("UI_LOG"):
                super().log_message(fmt, *args)

    return Handler


def serve(host: str, port: int, url: str) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(Store(url)))


def main():
    host = os.environ.get("UI_HOST", "127.0.0.1")
    port = int(os.environ.get("UI_PORT") or 8100)
    srv = serve(host, port, database_url())
    print(f"the UI on http://{host}:{port}/", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
