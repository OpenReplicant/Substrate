"""Content types: a JSON Schema in, a table, an API view, triggers and grants out (BRIEF.md section 2).

Every type's table has the same frame: id, slug, title, created_at, updated_at, created_by, updated_by. Each
property of the schema adds one column. Changes are additive: a new property adds a column; a property that
is gone keeps its column (dropping data is a migration the owner writes). The API view `api.<type>` is what
PostgREST serves at `/api/<type>`.
"""
from __future__ import annotations

import json
import re

from psycopg import sql

NAME = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
FRAME = ("id", "slug", "title", "created_at", "updated_at", "created_by", "updated_by")
RESERVED_TYPES = {"claims", "content_types", "login", "whoami", "rpc"}


def column_type(prop: dict) -> str:
    """A JSON Schema property's Postgres type. Anything structured is jsonb."""
    t = prop.get("type")
    if isinstance(t, list):
        t = next((x for x in t if x != "null"), "string")
    fmt = prop.get("format")
    if t == "string":
        return {"date-time": "timestamptz", "date": "date", "uuid": "uuid"}.get(fmt, "text")
    return {"integer": "bigint", "number": "double precision", "boolean": "boolean"}.get(t, "jsonb")


def check(type_id: str, schema: dict) -> list[str]:
    """What is wrong with a type before anything is created (empty when it is fine)."""
    problems = []
    if not NAME.match(type_id) or type_id in RESERVED_TYPES:
        problems.append(f"type id {type_id!r}: lowercase letters, digits and _, not one of {sorted(RESERVED_TYPES)}")
    if schema.get("type", "object") != "object":
        problems.append("a content type's schema is an object schema")
    for name in (schema.get("properties") or {}):
        if not NAME.match(name):
            problems.append(f"property {name!r}: lowercase letters, digits and _")
    return problems


def register(cur, type_id: str, schema: dict, plugin: str | None) -> dict:
    """Create or extend the type's table, view, triggers and grants; record it in wb.content_type."""
    problems = check(type_id, schema)
    if problems:
        raise ValueError("; ".join(problems))
    table = sql.Identifier("content", type_id)
    view = sql.Identifier("api", type_id)
    cur.execute(sql.SQL("""
        create table if not exists {t} (
          id          uuid primary key default gen_random_uuid(),
          slug        text unique check (slug ~ '^[a-z0-9][a-z0-9._-]*$'),
          title       text not null,
          created_at  timestamptz not null default now(),
          updated_at  timestamptz not null default now(),
          created_by  text,
          updated_by  text)""").format(t=table))
    cur.execute("select column_name from information_schema.columns where table_schema = 'content' and table_name = %s",
                (type_id,))
    have = {r[0] for r in cur.fetchall()}
    added = []
    for name, prop in (schema.get("properties") or {}).items():
        if name in FRAME or name in have:
            continue
        cur.execute(sql.SQL("alter table {t} add column {c} " + column_type(prop)).format(
            t=table, c=sql.Identifier(name)))
        added.append(name)
        if prop.get("description"):
            cur.execute(sql.SQL("comment on column {t}.{c} is {d}").format(
                t=table, c=sql.Identifier(name), d=sql.Literal(prop["description"])))
    for trigger, when, fn in (("wb_touch", "before", "wb.touch"), ("wb_claims", "after", "wb.record_claims")):
        cur.execute(sql.SQL("drop trigger if exists {g} on {t}").format(g=sql.Identifier(trigger), t=table))
        cur.execute(sql.SQL("create trigger {g} " + when + " insert or update on {t} for each row execute function "
                            + fn + "()").format(g=sql.Identifier(trigger), t=table))
    cur.execute(sql.SQL("create or replace view {v} with (security_invoker = true) as select * from {t}").format(
        v=view, t=table))
    label = schema.get("title") or type_id
    cur.execute(sql.SQL("comment on view {v} is {d}").format(v=view, d=sql.Literal(schema.get("description") or label)))
    # Viewers read; editors (and owners, who are editors too) add and change. Nobody deletes (BRIEF.md 2).
    for obj in (table, view):
        cur.execute(sql.SQL("grant select on {o} to wb_viewer").format(o=obj))
        cur.execute(sql.SQL("grant insert, update on {o} to wb_editor").format(o=obj))
    cur.execute("""insert into wb.content_type (id, plugin, label, schema) values (%s, %s, %s, %s)
                   on conflict (id) do update set label = excluded.label, schema = excluded.schema,
                     plugin = excluded.plugin, updated_at = now(),
                     version = wb.content_type.version + (wb.content_type.schema is distinct from excluded.schema)::int""",
                (type_id, plugin, label, json.dumps(schema)))
    return {"type": type_id, "added": added}
