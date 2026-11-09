"""The workbench command.

    workbench migrate                       create the database, roles and core schema; apply what is new
    workbench plugin load DIR               register a plugin: its content types, its vocabulary and their terms
    workbench type add SCHEMA.json [--plugin ID]
    workbench user add NAME [--role owner|editor|viewer]    prints a new password once
    workbench user reset NAME                               prints a new password once
    workbench user disable NAME                             signs them out of new sessions; nothing is deleted
    workbench user list
    workbench token NAME [--hours H] [--header]             a token for a person or an agent (for MCP's headersHelper)
    workbench serve [--port 8100]                           the server: plugins, extractors, live events
    workbench extract PLUGIN:NAME [--input KEY=VALUE ...] [--queue]   run an extractor now, or queue it
    workbench graph mapping DIR             write an Ontop mapping and ontology generated from the terms (graph.py)
    workbench graph project                 register and build pgGraph's projection of every content type

Settings (environment):
    WORKBENCH_ADMIN_URL              a Postgres superuser URL for the server (its database part is ignored)
    WORKBENCH_DB                     the database (default: workbench)
    WORKBENCH_AUTHENTICATOR_PASSWORD the password PostgREST's login, wb_authenticator, gets
    WORKBENCH_JWT_SECRET             signs sign-in tokens; PostgREST verifies them with the same value (32+ chars)
    WORKBENCH_SERVER_PASSWORD        the password the server's login, wb_server, gets
    WORKBENCH_READER_PASSWORD        the password the read-only login, wb_reader, gets (e.g. for a SPARQL endpoint)
    WB_PLUGINS_DIR                   where installed plugins are (serve, extract)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sys
from pathlib import Path

import psycopg
import yaml
from psycopg import sql

from . import types, vocab

HERE = Path(__file__).resolve().parent
ROLES = {"owner": "wb_owner", "editor": "wb_editor", "viewer": "wb_viewer"}
PLUGIN_API = "1"


def url(database: str) -> str:
    base = os.environ["WORKBENCH_ADMIN_URL"]
    return psycopg.conninfo.make_conninfo(base, dbname=database)


def connect(database: str | None = None) -> psycopg.Connection:
    return psycopg.connect(url(database or os.environ.get("WORKBENCH_DB", "workbench")), autocommit=False)


def migrate() -> dict:
    db = os.environ.get("WORKBENCH_DB", "workbench")
    out = {"database": db, "created": False, "applied": []}
    with psycopg.connect(url("postgres"), autocommit=True) as conn:
        if not conn.execute("select 1 from pg_database where datname = %s", (db,)).fetchone():
            conn.execute(sql.SQL("create database {}").format(sql.Identifier(db)))
            out["created"] = True
        # roles belong to the whole server: PostgREST's login and the four it switches to
        for role in ("wb_anon", "wb_viewer", "wb_editor", "wb_owner"):
            if not conn.execute("select 1 from pg_roles where rolname = %s", (role,)).fetchone():
                conn.execute(sql.SQL("create role {} nologin").format(sql.Identifier(role)))
        if not conn.execute("select 1 from pg_roles where rolname = 'wb_authenticator'").fetchone():
            conn.execute("create role wb_authenticator login noinherit")
        if not conn.execute("select 1 from pg_roles where rolname = 'wb_server'").fetchone():
            conn.execute("create role wb_server login")      # the Workbench server: plugins, extractors, events
        server_pw = os.environ.get("WORKBENCH_SERVER_PASSWORD")
        if server_pw:
            conn.execute(sql.SQL("alter role wb_server password {}").format(sql.Literal(server_pw)))
        conn.execute("grant wb_editor to wb_server")
        if not conn.execute("select 1 from pg_roles where rolname = 'wb_reader'").fetchone():
            conn.execute("create role wb_reader login")      # read-only views over the store (a SPARQL endpoint)
        reader_pw = os.environ.get("WORKBENCH_READER_PASSWORD")
        if reader_pw:
            conn.execute(sql.SQL("alter role wb_reader password {}").format(sql.Literal(reader_pw)))
        conn.execute("grant wb_viewer to wb_reader")
        password = os.environ.get("WORKBENCH_AUTHENTICATOR_PASSWORD")
        if password:
            conn.execute(sql.SQL("alter role wb_authenticator password {}").format(sql.Literal(password)))
        conn.execute("grant wb_viewer to wb_editor")
        conn.execute("grant wb_editor to wb_owner")
        for role in ("wb_anon", "wb_viewer", "wb_editor", "wb_owner"):
            conn.execute(sql.SQL("grant {} to wb_authenticator").format(sql.Identifier(role)))
    with connect(db) as conn:
        conn.execute("create table if not exists public.wb_migration (id text primary key, sha256 text not null,"
                     " applied_at timestamptz not null default now())")
        done = {r[0]: r[1] for r in conn.execute("select id, sha256 from public.wb_migration")}
        for f in sorted((HERE / "sql").glob("*.sql")):
            body = f.read_text()
            sha = hashlib.sha256(body.encode()).hexdigest()
            if f.name in done:
                if done[f.name] != sha:
                    raise SystemExit(f"{f.name} changed after it was applied: write a new migration instead")
                continue
            conn.execute(body)
            conn.execute("insert into public.wb_migration (id, sha256) values (%s, %s)", (f.name, sha))
            out["applied"].append(f.name)
        if any(f >= "009" for f in done) or any(f >= "009" for f in out["applied"]):
            with conn.cursor() as cur:
                vocab.load_core(cur)                     # Workbench's own terms (vocabulary.yaml)
        conn.execute("grant connect on database " + sql.Identifier(db).as_string(conn) + " to wb_authenticator, wb_server, wb_reader")
        # every content type registered before migration 004 gains its live-event trigger
        if any(f.startswith("004") for f in out["applied"]):
            with conn.cursor() as cur:
                for type_id, schema, plugin in cur.execute("select id, schema, plugin from wb.content_type").fetchall():
                    types.register(cur, type_id, schema, plugin)
        secret = os.environ.get("WORKBENCH_JWT_SECRET")
        if secret:
            if len(secret) < 32:
                raise SystemExit("WORKBENCH_JWT_SECRET must be at least 32 characters")
            conn.execute("insert into wb_private.setting (key, value) values ('jwt_secret', %s)"
                         " on conflict (key) do update set value = excluded.value", (secret,))
        reload(conn)
    return out


def reload(conn) -> None:
    conn.execute("notify pgrst, 'reload schema'")   # PostgREST refreshes its schema cache (v16.5 docs)


def add_type(path: Path, plugin: str | None) -> dict:
    schema = json.loads(path.read_text())
    type_id = schema.get("x-workbench-type") or path.stem
    with connect() as conn, conn.cursor() as cur:
        result = types.register(cur, type_id, schema, plugin)
        reload(conn)
    return result


def load_plugin(folder: Path) -> dict:
    manifest = yaml.safe_load((folder / "plugin.yaml").read_text())
    pid, version = manifest["id"], str(manifest.get("version", "0"))
    want = str((manifest.get("requires") or {}).get("workbench", PLUGIN_API))
    if want != PLUGIN_API:
        raise SystemExit(f"plugin {pid} needs plugin API {want}; this workbench serves {PLUGIN_API}")
    registered = []
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""insert into wb.plugin (id, version, path) values (%s, %s, %s)
                       on conflict (id) do update set version = excluded.version, path = excluded.path, loaded_at = now()""",
                    (pid, version, str(folder)))
        for pattern in manifest.get("content_types") or []:
            for f in sorted(folder.glob(pattern)):
                schema = json.loads(f.read_text())
                registered.append(types.register(cur, schema.get("x-workbench-type") or f.stem, schema, pid))
        vocab.load_core(cur)
        listed = vocab.load(cur, yaml.safe_load((folder / manifest["vocabulary"]).read_text()), pid) if manifest.get("vocabulary") else []
        terms = vocab.for_types(cur, pid, listed)
        reload(conn)
    if (folder / "plugin.yaml").is_file():          # new types are new node tables: project the graph again
        from . import graph
        with connect() as conn:
            graph.project(conn)
    return {"plugin": pid, "version": version, "types": registered, "terms": len(terms)}


def new_password() -> str:
    return secrets.token_urlsafe(18)


def user(action: str, name: str | None, role: str) -> dict | list:
    with connect() as conn:
        if action == "list":
            return [{"name": n, "role": r.removeprefix("wb_"), "disabled": d}
                    for n, r, d in conn.execute("select name, role, disabled from wb_private.person order by name")]
        if action == "disable":
            if not conn.execute("update wb_private.person set disabled = true where name = %s", (name,)).rowcount:
                raise SystemExit(f"no person named {name}")
            return {"name": name, "disabled": True}
        password = new_password()
        if action == "add":
            conn.execute("insert into wb_private.person (name, pass, role) values"
                         " (%s, wb_crypto.crypt(%s, wb_crypto.gen_salt('bf')), %s)", (name, password, ROLES[role]))
        else:
            n = conn.execute("update wb_private.person set pass = wb_crypto.crypt(%s, wb_crypto.gen_salt('bf'))"
                             " where name = %s", (password, name)).rowcount
            if not n:
                raise SystemExit(f"no person named {name}")
    return {"name": name, "password": password, "note": "shown once; sign in at /api/rpc/login"}


def token(name: str, hours: float) -> str:
    """A JWT for an existing, enabled person, as api.login would sign it. For agents, which sign in by token."""
    import base64, hashlib, hmac, time
    secret = os.environ["WORKBENCH_JWT_SECRET"]
    with connect() as conn:
        row = conn.execute("select role from wb_private.person where name = %s and not disabled", (name,)).fetchone()
    if not row:
        raise SystemExit(f"no enabled person named {name} (workbench user add {name} --role editor --agent)")
    enc = lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")  # noqa: E731
    head = enc(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = enc(json.dumps({"role": row[0], "name": name, "exp": int(time.time() + hours * 3600)}, separators=(",", ":")).encode())
    sig = enc(hmac.new(secret.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest())
    return f"{head}.{body}.{sig}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="workbench", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    p = sub.add_parser("plugin"); p.add_argument("action", choices=["load"]); p.add_argument("dir", type=Path)
    t = sub.add_parser("type"); t.add_argument("action", choices=["add"]); t.add_argument("schema", type=Path)
    t.add_argument("--plugin")
    u = sub.add_parser("user"); u.add_argument("action", choices=["add", "reset", "disable", "list"])
    u.add_argument("name", nargs="?"); u.add_argument("--role", choices=sorted(ROLES), default="owner")
    u.add_argument("--agent", action="store_true", help="an agent: it signs in by token, so its password is not shown")
    k = sub.add_parser("token"); k.add_argument("name"); k.add_argument("--hours", type=float, default=1.0)
    k.add_argument("--header", action="store_true", help='print {"Authorization": "Bearer ..."} for a headersHelper')
    s = sub.add_parser("serve"); s.add_argument("--port", type=int, default=8100); s.add_argument("--host", default="0.0.0.0")
    e = sub.add_parser("extract"); e.add_argument("extractor"); e.add_argument("--input", action="append", default=[])
    e.add_argument("--queue", action="store_true", help="put it on the server's queue instead of running it here")
    g = sub.add_parser("graph", help="graph views generated from the terms: an Ontop mapping, pgGraph's projection")
    g.add_argument("action", choices=["mapping", "project"]); g.add_argument("dir", type=Path, nargs="?")
    a = ap.parse_args(argv)
    if a.cmd == "graph":
        from . import graph
        with connect() as conn:
            if a.action == "project":
                result = graph.project(conn)
            else:
                if not a.dir:
                    ap.error("graph mapping needs a DIR to write mapping.obda and ontology.ttl to")
                a.dir.mkdir(parents=True, exist_ok=True)
                obda, ttl = graph.mapping(conn), graph.ontology(conn)
                changed = []
                for name, text in (("mapping.obda", obda), ("ontology.ttl", ttl)):
                    f = a.dir / name
                    if not f.is_file() or f.read_text() != text:
                        f.write_text(text)
                        changed.append(name)
                result = {"dir": str(a.dir), "changed": changed, "mappings": obda.count("mappingId"),
                          "terms": ttl.count(" a owl:")}
        print(json.dumps(result, indent=2))
        return 0
    if a.cmd == "token":
        tok = token(a.name, a.hours)
        print(json.dumps({"Authorization": f"Bearer {tok}"}) if a.header else tok)
        return 0
    if a.cmd == "serve":
        import uvicorn
        uvicorn.run("workbench.server:app", host=a.host, port=a.port, log_level="info")
        return 0
    if a.cmd == "extract":
        from .extract import Plugins, run_extractor
        inputs = dict(kv.split("=", 1) for kv in a.input)
        if a.queue:
            with connect() as conn:
                msg = conn.execute("select pgmq.send('wb_jobs', %s)", (json.dumps({"extractor": a.extractor, "inputs": inputs, "requested_by": "cli"}),)).fetchone()[0]
            print(json.dumps({"queued": msg}))
            return 0
        plugins = Plugins().load(Path(os.environ.get("WB_PLUGINS_DIR", "plugins")))
        result = run_extractor(connect, plugins, a.extractor, inputs)
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    if a.cmd == "migrate":
        result = migrate()
    elif a.cmd == "plugin":
        result = load_plugin(a.dir)
    elif a.cmd == "type":
        result = add_type(a.schema, a.plugin)
    else:
        if a.action != "list" and not a.name:
            ap.error("user add, reset and disable need a NAME")
        result = user(a.action, a.name, a.role)
        if getattr(a, "agent", False) and isinstance(result, dict):
            result = {"name": result["name"], "agent": True, "note": "signs in by token: workbench token " + result["name"]}
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
