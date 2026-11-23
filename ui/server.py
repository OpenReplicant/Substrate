"""The UI's server (plan step 3b; S-140): the store's pages and maps, read-only, on the standard library.

    python3 -m ui.server                     # 127.0.0.1:UI_PORT (8100); the kernel is KERNEL_URL, libpq's PG* or .env's

The entities, search, pages and maps come from the Knowledge Kernel's `substrate` schema (modules/view-substrate in
the kernel's repository; S-153, S-154), in the database KERNEL_URL names (default: database `kernel` in the same
Postgres, as the kernel's own login), read as the module's role kkm_view_substrate so the kernel's row-level security
applies. Entity ids are the Q numbers Substrate's
store gave: urn:kk:substrate:Q10 in the kernel, Q10 here.

In the stack it is the compose service `ui` (deploy/compose.yaml), published on 127.0.0.1:UI_PORT.

  GET /                         the page (ui/static/index.html); routes are in its hash: #/map/Q10, #/e/Q10
  GET /static/...               ui/static
  GET /api/search?q=...         entities by label, alias, key or page words
  GET /api/wholes               entities with parts: what has a map
  GET /api/entity/Q10           label, description, the page (substrate.page) and whether it has a map
  GET /api/map/Q10[?depth=6]    nodes (id, label, description, kind) and edges (source, target, kind, statement,
                                flagged): substrate.map_nodes and substrate.map (statement: the claim's id)

Every response carries the UI's Content-Security-Policy (deploy/caddy/Caddyfile's, without frames): scripts and
styles only from this origin. Reads are on a read-only session; the store's writes go through the agent's tools
(the kernel's MCP server, profile substrate). The old assistant's pages (the companion's and the worker's, with the
owner's writes) were retired in S-194.
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
    """One read-only connection, used by one request at a time. With a role, every session switches to it first (the
    kernel's read model runs as its own role)."""

    def __init__(self, url: str, role: str | None = None):
        self.url, self.lock, self.conn, self.role = url, threading.Lock(), None, role
        self.options = "-c statement_timeout=10000 -c default_transaction_read_only=on"

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


def api(path: str, q: dict, kernel: Store) -> tuple[int, object]:
    """kernel: the kernel's read model."""
    return from_kernel(kernel, path.strip("/").split("/")[1:], q)   # the parts after "api"


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


def handler(kernel: Store):
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
                    status, obj = api(u.path, parse_qs(u.query), kernel)
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

        def log_message(self, fmt, *args):
            if os.environ.get("UI_LOG"):
                super().log_message(fmt, *args)

    return Handler


def serve(host: str, port: int, kernel: str) -> ThreadingHTTPServer:
    """kernel: the kernel's database, for the entities, pages and maps."""
    return ThreadingHTTPServer((host, port), handler(Store(kernel, role=KERNEL_ROLE)))


def main():
    host = os.environ.get("UI_HOST", "127.0.0.1")
    port = int(os.environ.get("UI_PORT") or 8100)
    srv = serve(host, port, kernel_url())
    print(f"the UI on http://{host}:{port}/", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
