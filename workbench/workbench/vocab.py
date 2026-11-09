"""Vocabularies (BRIEF.md section 4): terms in wb.term, named by content types and fields with `x-term`.

A vocabulary file (Workbench's own, vocabulary.yaml, and any plugin's `vocabulary:` in plugin.yaml) lists prefixes
and terms; CURIEs expand against them. Each content type and field has a term: the one its `x-term` names, or a
default under the base (type/<type>, field/<type>/<field>); a relation predicate is the property whose
`predicate` names it, or rel/<predicate> under wb:relatedTo. Loading is idempotent: a plugin's terms are what its
files and types say now.
"""
from __future__ import annotations

from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
CORE = yaml.safe_load((HERE / "vocabulary.yaml").read_text())
BASE = CORE["base"]
WB = CORE["prefixes"]["wb"]
KINDS = {"class", "property", "datatype-property", "value"}
SCALAR = {"text", "bigint", "double precision", "boolean", "timestamptz", "date", "uuid"}


def expand(term: str | None, prefixes: dict) -> str | None:
    if not term:
        return None
    if term.startswith(("http://", "https://", "urn:")):
        return term
    prefix, sep, local = term.partition(":")
    if not sep or prefix not in prefixes:
        raise ValueError(f"term {term!r}: no prefix {prefix!r} (known: {', '.join(sorted(prefixes))})")
    return prefixes[prefix] + local


def prefixes(cur) -> dict:
    out = dict(CORE["prefixes"])
    out.update({label: iri for iri, label in cur.execute("select iri, label from wb.term where kind = 'prefix'").fetchall()})
    return out


def type_iri(type_id: str, schema: dict, pre: dict) -> str:
    return expand(schema.get("x-term"), pre) or f"{BASE}type/{type_id}"


def field_iri(type_id: str, field: str, prop: dict, pre: dict) -> str:
    return expand((prop or {}).get("x-term"), pre) or f"{BASE}field/{type_id}/{field}"


def predicate_iri(predicate: str, cur) -> str:
    row = cur.execute("select iri from wb.term where predicate = %s order by plugin nulls last limit 1", (predicate,)).fetchone()
    return row[0] if row else f"{BASE}rel/{predicate}"


def _put(cur, t: dict, vocabulary: str, plugin: str | None, pre: dict) -> str:
    kind = t.get("kind", "class")
    if kind not in KINDS:
        raise ValueError(f"term {t.get('iri')}: kind {kind!r} is not one of {sorted(KINDS)}")
    iri = expand(t["iri"], pre)
    cur.execute("""insert into wb.term (iri, label, kind, vocabulary, comment, parents, characteristics, inverse_of, domain,
                                        range, plugin, predicate)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   on conflict (iri) do update set label = excluded.label, kind = excluded.kind, vocabulary = excluded.vocabulary,
                     comment = excluded.comment, parents = excluded.parents, characteristics = excluded.characteristics,
                     inverse_of = excluded.inverse_of, domain = excluded.domain, range = excluded.range,
                     plugin = excluded.plugin, predicate = excluded.predicate""",
                (iri, t.get("label"), kind, vocabulary, t.get("comment"), [expand(p, pre) for p in t.get("parents") or []],
                 t.get("characteristics") or [], expand(t.get("inverse_of"), pre), expand(t.get("domain"), pre),
                 expand(t.get("range"), pre), plugin, t.get("predicate")))
    return iri


def load(cur, data: dict, plugin: str | None) -> list[str]:
    """A vocabulary file's prefixes and terms into wb.term, as plugin (None for Workbench's own)."""
    name = data.get("vocabulary") or plugin or "workbench"
    for label, iri in (data.get("prefixes") or {}).items():
        cur.execute("""insert into wb.term (iri, label, kind, vocabulary, plugin) values (%s, %s, 'prefix', %s, %s)
                       on conflict (iri) do update set label = excluded.label, vocabulary = excluded.vocabulary""",
                    (iri, label, name, plugin))
    pre = prefixes(cur)
    pre.update(data.get("prefixes") or {})
    return [_put(cur, t, name, plugin, pre) for t in data.get("terms") or []]


def for_types(cur, plugin: str | None, vocabulary_terms: list[str]) -> list[str]:
    """Every term the plugin's content types and fields name, added where the vocabulary did not already; then
    the plugin's terms that nothing names any more are removed."""
    pre = prefixes(cur)
    named = set(vocabulary_terms)
    rows = cur.execute("select id, schema from wb.content_type where plugin is not distinct from %s", (plugin,)).fetchall()
    for type_id, schema in rows:
        cls = type_iri(type_id, schema, pre)
        named.add(cls)
        cur.execute("""insert into wb.term (iri, label, kind, vocabulary, parents, plugin) values (%s, %s, 'class', %s, %s, %s)
                       on conflict (iri) do nothing""",
                    (cls, schema.get("title") or type_id, plugin or "workbench", [WB + "Item"], plugin))
        for field, prop in (schema.get("properties") or {}).items():
            iri = field_iri(type_id, field, prop, pre)
            named.add(iri)
            cur.execute("""insert into wb.term (iri, label, kind, vocabulary, comment, domain, plugin)
                           values (%s, %s, 'datatype-property', %s, %s, %s, %s) on conflict (iri) do nothing""",
                        (iri, field, plugin or "workbench", (prop or {}).get("description"), cls, plugin))
    cur.execute("delete from wb.term where plugin is not distinct from %s and kind <> 'prefix' and not (iri = any(%s))",
                (plugin, sorted(named)))
    return sorted(named)


def load_core(cur) -> list[str]:
    return load(cur, CORE, None)
