"""The workbench command.

    workbench migrate                       create the database, roles and core schema; apply what is new
    workbench plugin load DIR               register a plugin: its content types (and, later, its code)
    workbench type add SCHEMA.json [--plugin ID]
    workbench user add NAME [--role owner|editor|viewer]    prints a new password once
    workbench user reset NAME                               prints a new password once
    workbench user disable NAME                             signs them out of new sessions; nothing is deleted
    workbench user list

Settings (environment):
    WORKBENCH_ADMIN_URL              a Postgres superuser URL for the server (its database part is ignored)
    WORKBENCH_DB                     the database (default: workbench)
    WORKBENCH_AUTHENTICATOR_PASSWORD the password PostgREST's login, wb_authenticator, gets
    WORKBENCH_JWT_SECRET             signs sign-in tokens; PostgREST verifies them with the same value (32+ chars)
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

from . import types

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
        conn.execute("grant connect on database " + sql.Identifier(db).as_string(conn) + " to wb_authenticator")
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
        reload(conn)
    return {"plugin": pid, "version": version, "types": registered}


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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="workbench", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    p = sub.add_parser("plugin"); p.add_argument("action", choices=["load"]); p.add_argument("dir", type=Path)
    t = sub.add_parser("type"); t.add_argument("action", choices=["add"]); t.add_argument("schema", type=Path)
    t.add_argument("--plugin")
    u = sub.add_parser("user"); u.add_argument("action", choices=["add", "reset", "disable", "list"])
    u.add_argument("name", nargs="?"); u.add_argument("--role", choices=sorted(ROLES), default="owner")
    a = ap.parse_args(argv)
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
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
