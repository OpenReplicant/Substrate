"""The store (S-135): Wikibase's data model in Postgres with OpenWiki's pinned evidence. The rules live in the
schema (store/sql/); this is a thin way to write and read it.

    from store import Store, person, interpreter, parser, rule
    s = Store(conn, actor="claude-code")              # who the revisions name
    with s.edit("what this edit does"):               # one transaction, one revision per entity it touches
        q = s.item("Workbench", key="workbench", description="...")
        p = s.property("lifecycle", "string", key="lifecycle")
        s.say(q, p, "production", by=person("pete"))
    s.render(q); s.search("work"); s.expand(q); s.locate(q)

`conn` is a psycopg connection with autocommit on (each call outside `edit` is its own transaction).
"""
from __future__ import annotations

import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from psycopg.types.json import Jsonb

SQL = Path(__file__).parent / "sql"
SOME, NONE = object(), object()       # Wikibase's "unknown value" and "no value"


def migrate(conn) -> list[str]:
    """Apply the schema files not yet applied, each in its own transaction; returns their names."""
    conn.execute("create table if not exists public.store_migration (name text primary key, applied_at timestamptz not null default now())")
    done = {r[0] for r in conn.execute("select name from public.store_migration")}
    applied = []
    for f in sorted(SQL.glob("*.sql")):
        if f.name in done:
            continue
        with conn.transaction():
            conn.execute(f.read_text())
            conn.execute("insert into public.store_migration (name) values (%s)", (f.name,))
        applied.append(f.name)
    return applied


def project(conn) -> dict:
    """Build pgGraph's graph of usable entity-valued statements (outside a transaction: pgGraph builds apart from
    the one that registered its tables). Its triggers keep it current from then on."""
    nodes, edges = conn.execute("select nodes_loaded, edges_loaded from graph.build()").fetchone()
    return {"nodes": nodes, "edges": edges}


@dataclass(frozen=True)
class Ref:
    """Who stated something, and the span it rests on (a span id from Store.read_source)."""
    kind: str
    name: str
    version: str | None = None
    run: str | None = None
    span: str | None = None
    premises: tuple = field(default_factory=tuple)
    note: str | None = None


def person(name, span=None, note=None):
    return Ref("person", name, span=span, note=note)


def interpreter(name, version, span=None, note=None):
    """A claim's author: the LLM, a distilled component or Claude Code, with its version."""
    return Ref("interpreter", name, version=version, span=span, note=note)


def parser(name, run, span=None, note=None):
    return Ref("parser", name, run=run, span=span, note=note)


def rule(name, premises, note=None):
    """A derivation: its premises are the statements it rests on, so a flag on any of them reaches it."""
    return Ref("rule", name, premises=tuple(str(p) for p in premises), note=note)


def paragraphs(text: str) -> list[tuple[str, str]]:
    """A text cut at blank lines: [("p1", ...), ...]."""
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return [(f"p{i}", p) for i, p in enumerate(parts, 1)]


def time_value(v: str) -> dict:
    """'2026', '2026-11' or '2026-11-17' as a Wikidata time value with its precision."""
    m = re.fullmatch(r"(-?)(\d{1,16})(?:-(\d\d)(?:-(\d\d))?)?", v)
    if not m:
        raise ValueError(f"not a date: {v!r}")
    sign, y, mo, d = m.groups()
    precision = 11 if d else 10 if mo else 9
    return {"time": f"{'-' if sign else '+'}{y.zfill(4)}-{mo or '00'}-{d or '00'}T00:00:00Z", "precision": precision}


class Store:
    def __init__(self, conn, actor: str):
        self.c = conn
        self._types: dict[str, str | None] = {}
        conn.execute("select set_config('store.actor', %s, false)", (actor,))

    @contextmanager
    def edit(self, summary: str | None = None):
        with self.c.transaction():
            self.c.execute("select set_config('store.summary', %s, true)", (summary or "",))
            yield self

    # Writing ------------------------------------------------------------------------------------------

    def _entity(self, kind, label, key, description, datatype, aliases, prose):
        if key is not None:
            row = self.c.execute("select id, label, description, aliases, prose from store.entity where key = %s", (key,)).fetchone()
            if row:
                want = (label, description, list(aliases or []), prose)
                if (row[1], row[2], row[3], row[4]) != want:
                    self.c.execute("update store.entity set label = %s, description = %s, aliases = %s, prose = %s where id = %s",
                                   (*want, row[0]))
                return row[0]
        return self.c.execute("select store.new_entity(%s, %s, %s, %s, %s, %s, %s)",
                              (kind, label, key, description, datatype, list(aliases or []), prose)).fetchone()[0]

    def item(self, label, key=None, description=None, aliases=(), prose=None) -> str:
        """Make an item, or with a key find it and bring its label, description, aliases and prose up to date."""
        return self._entity("item", label, key, description, None, aliases, prose)

    def property(self, label, datatype, key=None, description=None, aliases=()) -> str:
        return self._entity("property", label, key, description, datatype, aliases, None)

    def id(self, key: str) -> str:
        row = self.c.execute("select id from store.entity where key = %s", (key,)).fetchone()
        if not row:
            raise KeyError(key)
        return row[0]

    def datatype(self, prop: str) -> str | None:
        if prop not in self._types:
            row = self.c.execute("select datatype from store.entity where id = %s", (prop,)).fetchone()
            self._types[prop] = row[0] if row else None
        return self._types[prop]

    def _encode(self, prop, value):
        if value is SOME:
            return "somevalue", None, None
        if value is NONE:
            return "novalue", None, None
        dt = self.datatype(prop)
        if dt in ("item", "property"):
            return "value", None, value
        if dt == "quantity" and isinstance(value, (int, float, Decimal)):
            value = {"amount": value}
        elif dt == "time" and isinstance(value, str):
            value = time_value(value)
        elif dt == "coordinate" and isinstance(value, (tuple, list)):
            value = {"latitude": value[0], "longitude": value[1]}
        if isinstance(value, dict):
            value = {k: (float(v) if isinstance(v, Decimal) else v) for k, v in value.items()}
        return "value", Jsonb(value), None

    def say(self, subject, prop, value, *, by: Ref | list[Ref], qualifiers=(), rank="normal") -> str:
        """A statement and its references; qualifiers are (property, value) pairs. Returns its id."""
        refs = [by] if isinstance(by, Ref) else list(by)
        if not refs:
            raise ValueError("a statement says who stated it")
        with self.c.transaction():
            snak, v, ve = self._encode(prop, value)
            sid = self.c.execute("insert into store.statement (subject, property, snak, value, value_entity, rank) "
                                 "values (%s, %s, %s, %s, %s, %s) returning id", (subject, prop, snak, v, ve, rank)).fetchone()[0]
            for i, (qp, qv) in enumerate(qualifiers):
                self._qualify(sid, i, qp, qv)
            for r in refs:
                self.cite(sid, r)
        return str(sid)

    def _qualify(self, sid, ord_, prop, value):
        snak, v, ve = self._encode(prop, value)
        self.c.execute("insert into store.qualifier (statement_id, ord, property, snak, value, value_entity) "
                       "values (%s, %s, %s, %s, %s, %s)", (sid, ord_, prop, snak, v, ve))

    def cite(self, statement, ref: Ref) -> str:
        return str(self.c.execute("select store.cite(%s, %s, %s, %s, %s, %s, %s::uuid[], %s)",
                                  (statement, ref.kind, ref.name, ref.version, ref.run, ref.span,
                                   list(ref.premises), ref.note)).fetchone()[0])

    def recite(self, statement, old_reference, ref: Ref) -> str:
        """After review of a flagged statement: cite the new reference in place of the old one."""
        with self.c.transaction():
            new = self.cite(statement, ref)
            self.c.execute("delete from store.cites where statement_id = %s and reference_id = %s", (statement, old_reference))
        return new

    def rank(self, statement, rank, reason=None):
        """Prefer, keep normal or deprecate a statement; a deprecation can say why."""
        with self.c.transaction():
            self.c.execute("update store.statement set rank = %s where id = %s", (rank, statement))
            if reason:
                n = self.c.execute("select coalesce(max(ord) + 1, 0) from store.qualifier where statement_id = %s", (statement,)).fetchone()[0]
                self._qualify(statement, n, self.id("reason-for-deprecated-rank"), reason)

    def constrain(self, prop, kind, by: Ref, **params) -> str:
        """A constraint on a property: kind is single-value, format (regex=), one-of (values=[...]) or
        value-type (classes=[...])."""
        q = [(self.id("format-as-regex"), params["regex"])] if kind == "format" else []
        q += [(self.id("item-of-property-constraint"), v) for v in params.get("values", [])]
        q += [(self.id("class"), c) for c in params.get("classes", [])]
        return self.say(prop, self.id("property-constraint"), self.id(f"{kind}-constraint"), by=by, qualifiers=q)

    def read_source(self, uri, spans, media_type=None) -> dict[str, tuple[str, str]]:
        """Read a source whole: spans as [(locator, text)] or {locator: text}. Returns {locator: (span id, change)},
        change being same, new, changed or gone."""
        items = spans.items() if isinstance(spans, dict) else spans
        rows = self.c.execute("select loc, span_id, change from store.read_source(%s, %s, %s)",
                              (uri, media_type, Jsonb([{"locator": k, "text": t} for k, t in items]))).fetchall()
        return {loc: (str(sid), ch) for loc, sid, ch in rows}

    def read_span(self, uri, locator, text, media_type=None) -> tuple[str, str]:
        """One span of a source (a quote), leaving its other spans alone. Returns (span id, change)."""
        sid, ch = self.c.execute("select span_id, change from store.read_span(%s, %s, %s, %s)",
                                 (uri, locator, text, media_type)).fetchone()
        return str(sid), ch

    def resolve(self, ref: str) -> str:
        """An entity by its id (Q12, P3) or its key."""
        return ref if re.fullmatch(r"[QP][1-9]\d*", ref) else self.id(ref)

    # Reading ------------------------------------------------------------------------------------------

    def alternatives(self, role) -> list[dict]:
        """What provides every interface a role requires, and whether (and where) it fills the role now."""
        rows = self.c.execute("select entity, label, fills_now, in_whole, provides from store.alternatives(%s)", (role,)).fetchall()
        return [{"entity": e, "label": la, "fills_now": f, "in_whole": w, "provides": pr} for e, la, f, w, pr in rows]

    def render(self, entity, all_ranks=False) -> str | None:
        return self.c.execute("select store.render(%s, %s)", (entity, all_ranks)).fetchone()[0]

    def search(self, query, limit=10) -> list[dict]:
        rows = self.c.execute("select id, label, description, score from store.search(%s, %s)", (query, limit)).fetchall()
        return [{"id": i, "label": la, "description": d, "score": round(s, 3)} for i, la, d, s in rows]

    def expand(self, entity) -> list[dict]:
        """One hop: the entity's usable statements, and the usable statements whose value it is."""
        rows = self.c.execute("""
            select 'out', u.id, u.property, p.label, u.value_entity, store.fmt(u.property, u.snak, u.value, u.value_entity), u.rank
            from store.usable u join store.entity p on p.id = u.property where u.subject = %(e)s
            union all
            select 'in', u.id, u.property, p.label, u.subject, format('%%s (%%s)', s.label, s.id), u.rank
            from store.usable u join store.entity p on p.id = u.property join store.entity s on s.id = u.subject
            where u.value_entity = %(e)s
            order by 1 desc, 4, 6""", {"e": entity}).fetchall()
        return [{"direction": d, "statement": str(sid), "property": p, "property_label": pl, "entity": ent,
                 "value": v, "rank": r} for d, sid, p, pl, ent, v, r in rows]

    def locate(self, target) -> list[dict]:
        """The evidence behind an entity's statements (all ranks) or one statement: each reference, its span's
        pinned text, whether the span has changed since, and a rule's premises."""
        where = "s.subject = %s" if re.fullmatch(r"[QP]\d+", str(target)) else "s.id = %s::uuid"
        rows = self.c.execute(f"""
            select s.id, store.gloss(s.id), s.rank, r.id, r.by_kind, r.by_name, r.by_version, r.run, r.note,
                   so.uri, sp.locator, sp.text, sp.hash, sp.superseded_at is not null,
                   (select array_agg(pr.statement_id::text order by pr.statement_id) from store.premise pr where pr.reference_id = r.id),
                   (select string_agg(distinct f.reason, '; ') from store.flag f where f.statement_id = s.id)
            from store.statement s join store.cites c on c.statement_id = s.id join store.reference r on r.id = c.reference_id
                 left join store.span sp on sp.id = r.span_id left join store.source so on so.id = sp.source_id
            where {where} order by s.created_at, s.id, r.created_at""", (target,)).fetchall()
        out = []
        for sid, gloss, rank, rid, kind, name, ver, run, note, uri, loc, text, h, changed, prem, flag in rows:
            ref = {"reference": str(rid), "by": kind, "name": name, "version": ver, "run": run, "note": note}
            if uri:
                ref["span"] = {"source": uri, "locator": loc, "text": text, "hash": h, "changed_since": changed}
            if prem:
                ref["premises"] = prem
            out.append({"statement": str(sid), "says": gloss, "rank": rank, "flagged": flag, **ref})
        return out

    def path(self, a, b, max_depth=12) -> list[dict]:
        """The shortest path from entity a to entity b along statements that are not deprecated, in their direction."""
        rows = self.c.execute("select step, entity, label, via, via_label, statement from store.path(%s, %s, %s)", (a, b, max_depth)).fetchall()
        return [{"step": s, "entity": e, "label": la, "via": v, "via_label": vl, "statement": str(st) if st else None}
                for s, e, la, v, vl, st in rows]

    def flags(self) -> list[dict]:
        rows = self.c.execute("select statement_id, span_id, via, reason, store.gloss(statement_id) from store.flag "
                              "order by reason, statement_id").fetchall()
        return [{"statement": str(s), "span": str(sp), "via": str(v) if v else None, "reason": r, "says": g}
                for s, sp, v, r, g in rows]

    def violations(self) -> list[dict]:
        rows = self.c.execute("select statement_id, subject, property, kind, message from store.violation "
                              "order by subject, property, kind").fetchall()
        return [{"statement": str(s), "subject": su, "property": p, "kind": k, "message": m} for s, su, p, k, m in rows]
