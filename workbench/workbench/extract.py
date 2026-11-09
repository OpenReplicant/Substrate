"""Server-side plugins and extractors (BRIEF.md sections 3 and 5).

A plugin's `server` module (named in its plugin.yaml) has `register(wb)`; `wb.extractor(name, fn)` adds an
extractor called `<plugin>:<name>`. An extractor is `fn(ctx, inputs)`: it reads its sources and writes through
`ctx`, and one run is one transaction, recorded in wb.run.

    ctx.source(uri, data, media_type)            a source it read (deduplicated by content), its id
    ctx.upsert(type, slug, fields, title=, source=, evidence={field: {quote, span}})   an item, its id
    ctx.relate(from_type, from_id, predicate, to_type, to_id)
    ctx.done(type)                               it read the whole source: retract what it no longer found
    ctx.decision(kind, key, subject, evidence)   raise something for a person (the review lane)
    ctx.log(message)

Writes go through the same `api` views PostgREST serves, as role wb_server (an editor), so the same triggers
record a claim for every value, here attributed to the extractor and carrying its source, quote and span.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import sys
import traceback
from pathlib import Path

import yaml
from psycopg import sql
from psycopg.types.json import Jsonb

PLUGIN_API = "1"


class ServerApi:
    """What a plugin's register(wb) gets."""

    def __init__(self, registry: "Plugins", plugin: str, folder: Path):
        self._r, self.plugin, self.folder = registry, plugin, folder

    def extractor(self, name: str, fn, description: str = "", inputs: dict | None = None):
        key = f"{self.plugin}:{name}"
        self._r.extractors[key] = {"key": key, "plugin": self.plugin, "name": name, "fn": fn,
                                   "description": description, "inputs": inputs or {}}

    def setting(self, name: str, default: str | None = None) -> str | None:
        """WB_<PLUGIN>_<NAME> from the environment, e.g. WB_SUBSTRATE_ROOT."""
        return os.environ.get(f"WB_{self.plugin.upper().replace('-', '_')}_{name.upper()}", default)


class Plugins:
    def __init__(self):
        self.extractors: dict[str, dict] = {}
        self.loaded: list[dict] = []

    def load(self, root: Path) -> "Plugins":
        """Every plugin folder under root with a server module."""
        for folder in sorted(p for p in root.iterdir() if (p / "plugin.yaml").is_file()):
            manifest = yaml.safe_load((folder / "plugin.yaml").read_text())
            want = str((manifest.get("requires") or {}).get("workbench", PLUGIN_API))
            entry = {"id": manifest["id"], "version": str(manifest.get("version", "0")), "server": manifest.get("server")}
            if want != PLUGIN_API:
                entry["error"] = f"needs plugin API {want}"
            elif manifest.get("server"):
                try:
                    if str(folder) not in sys.path:
                        sys.path.insert(0, str(folder))
                    module = importlib.import_module(manifest["server"])
                    module.register(ServerApi(self, manifest["id"], folder))
                except Exception as e:      # one broken plugin must not stop the others
                    entry["error"] = f"{type(e).__name__}: {e}"
            self.loaded.append(entry)
        return self

    def describe(self) -> list[dict]:
        return [{k: v for k, v in e.items() if k != "fn"} for e in self.extractors.values()]


class Context:
    def __init__(self, conn, extractor: dict, inputs: dict):
        self.conn, self.ex, self.inputs = conn, extractor, inputs
        self.author = extractor["key"]
        self.seen: dict[str, set] = {}
        self.relations: list[tuple] = []
        self.related_from: set[tuple] = set()
        self.keys: set[str] = set()
        self.counts = {"items": 0, "sources": 0, "relations": 0, "decisions": 0}
        self.messages: list[str] = []
        self.conn.execute("set local role wb_server")
        self.run = self.conn.execute(
            "insert into wb.run (extractor, plugin, inputs) values (%s, %s, %s) returning id",
            (self.author, extractor["plugin"], Jsonb(inputs))).fetchone()[0]
        self._set("wb.author", self.author)
        self._set("wb.run", str(self.run))

    def _set(self, key: str, value: str | None):
        self.conn.execute("select set_config(%s, %s, true)", (key, value or ""))

    def log(self, message: str):
        self.messages.append(str(message))

    def source(self, uri: str, data: bytes, media_type: str | None = None) -> str:
        sha = hashlib.sha256(data).hexdigest()
        row = self.conn.execute(
            "insert into wb.source (uri, sha256, media_type) values (%s, %s, %s)"
            " on conflict (uri, coalesce(sha256, '')) do nothing returning id", (uri, sha, media_type)).fetchone()
        if row:
            self.counts["sources"] += 1
            return str(row[0])
        return str(self.conn.execute("select id from wb.source where uri = %s and sha256 = %s", (uri, sha)).fetchone()[0])

    def upsert(self, type_id: str, slug: str, fields: dict, *, title: str | None = None,
               source: str | None = None, evidence: dict | None = None) -> str:
        cols = {r[0] for r in self.conn.execute(
            "select column_name from information_schema.columns where table_schema = 'api' and table_name = %s",
            (type_id,))}
        if not cols:
            raise ValueError(f"no content type {type_id!r}")
        values = {k: v for k, v in fields.items() if k in cols and k not in ("id", "slug", "title")}
        values["title"] = title or fields.get("title") or slug
        for k, v in values.items():
            if isinstance(v, (dict, list)):
                values[k] = Jsonb(v)
        self._set("wb.source", source)
        self._set("wb.evidence", json.dumps(evidence or {}))
        view = sql.Identifier("api", type_id)
        found = self.conn.execute(sql.SQL("select id, to_jsonb(x) from {} x where slug = %s").format(view), (slug,)).fetchone()
        if found:
            # only what changed: an unchanged item keeps its updated_at and updated_by, so "updated" means it
            now = found[1]
            changed = {k: v for k, v in values.items()
                       if json.dumps(v.obj if isinstance(v, Jsonb) else v, sort_keys=True, default=str)
                       != json.dumps(now.get(k), sort_keys=True, default=str)}
            if changed:
                assignments = sql.SQL(", ").join(sql.SQL("{} = %s").format(sql.Identifier(k)) for k in changed)
                self.conn.execute(sql.SQL("update {} set {} where id = %s").format(view, assignments),
                                  (*changed.values(), found[0]))
            item = str(found[0])
        else:
            names = ["slug", *values]
            item = str(self.conn.execute(sql.SQL("insert into {} ({}) values ({}) returning id").format(
                view, sql.SQL(", ").join(map(sql.Identifier, names)), sql.SQL(", ").join(sql.Placeholder() * len(names))),
                (slug, *values.values())).fetchone()[0])
        self.seen.setdefault(type_id, set()).add(item)
        self.counts["items"] += 1
        return item

    def relate(self, from_type: str, from_id: str, predicate: str, to_type: str, to_id: str):
        self.related_from.add((from_type, from_id))
        self.relations.append((from_type, from_id, predicate, to_type, to_id))

    def done(self, type_id: str) -> int:
        n = self.conn.execute("select wb.retract_missing(%s, %s, %s::uuid[])",
                              (self.author, type_id, list(self.seen.get(type_id, set())))).fetchone()[0]
        if n:
            self.log(f"{type_id}: {n} claims retracted (no longer in the source)")
        return n

    def decision(self, kind: str, key: str, subject: dict, evidence: list | None = None):
        self.keys.add(key)
        self.conn.execute(
            "insert into wb.decision (kind, key, raised_by, subject, evidence) values (%s, %s, %s, %s, %s)"
            " on conflict (raised_by, key) where status = 'open'"
            " do update set subject = excluded.subject, evidence = excluded.evidence",
            (kind, key, self.author, Jsonb(subject), Jsonb(evidence or [])))
        self.counts["decisions"] += 1

    def finish(self, withdraw: bool = True) -> dict:
        # relations: what this run read replaces what it read before, for the items it read them from
        for from_type, from_id in self.related_from:
            self.conn.execute("delete from wb.relation where from_type = %s and from_id = %s", (from_type, from_id))
        for rel in self.relations:
            self.conn.execute("insert into wb.relation (from_type, from_id, predicate, to_type, to_id)"
                              " values (%s, %s, %s, %s, %s) on conflict do nothing", rel)
        self.counts["relations"] = len(self.relations)
        withdrawn = 0
        if withdraw:
            withdrawn = self.conn.execute(
                "update wb.decision set status = 'withdrawn', decided_by = %s, decided_at = now(),"
                " note = 'no longer found' where raised_by = %s and status = 'open' and not (key = any(%s))",
                (self.author, self.author, list(self.keys))).rowcount
        outcome = {"ok": True, **self.counts, "withdrawn": withdrawn, "log": self.messages}
        self.conn.execute("update wb.run set ended_at = now(), outcome = %s where id = %s", (Jsonb(outcome), self.run))
        return {"run": str(self.run), **outcome}


def run_extractor(connect, plugins: Plugins, key: str, inputs: dict | None = None) -> dict:
    """Run one extractor in one transaction; a failure rolls its writes back and is recorded as a failed run."""
    ex = plugins.extractors.get(key)
    if not ex:
        raise KeyError(f"no extractor {key}; have {sorted(plugins.extractors)}")
    inputs = inputs or {}
    with connect() as conn:
        try:
            with conn.transaction():
                ctx = Context(conn, ex, inputs)
                ex["fn"](ctx, inputs)
                return ctx.finish(withdraw=inputs.get("withdraw", True) is not False)
        except Exception as e:
            err = {"ok": False, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-2000:]}
            with conn.transaction():
                conn.execute("set local role wb_server")
                conn.execute("insert into wb.run (extractor, plugin, inputs, ended_at, outcome) values (%s, %s, %s, now(), %s)",
                             (key, ex["plugin"], Jsonb(inputs), Jsonb(err)))
            return err
