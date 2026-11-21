"""The old `store` schema's writer, kept only to build fixtures for the one-off exporter (S-156).

Substrate's store (S-135) lives in the Knowledge Kernel now (S-153, S-154). Its schema (001_store.sql,
003_components.sql, 004_map.sql here) and this writer stay as test fixtures so the kernel's encoder-substrate, which
reads that schema from a machine that has not exported yet (scripts/kernel.sh export), is still tested end to end.
Nothing else imports this.

    from legacy import Store, person, interpreter, parser
    apply(conn)                                       # the three schema files, in order
    s = Store(conn, actor="test")
    with s.edit("what this edit does"):
        q = s.item("Workbench", key="workbench", description="...")
        s.say(q, s.id("instance-of"), s.id("role"), by=person("pete"))
"""
from __future__ import annotations

import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from psycopg.types.json import Jsonb

SQL = Path(__file__).parent
SOME, NONE = object(), object()       # Wikibase's "unknown value" and "no value"


def apply(conn) -> None:
    """The old schema's files the exporter reads (not the graph's, nor the env schema, which lives in environment/sql/)."""
    for f in ("001_store", "003_components", "004_map"):
        with conn.transaction():
            conn.execute((SQL / f"{f}.sql").read_text())

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
