"""Graph views over the same tables, never copies (BRIEF.md section 4): both generated from the terms, so they
cannot drift apart.

    ontop(conn)    an Ontop mapping (.obda) and ontology (Turtle) for SPARQL over the live tables: each content
                   type's items as its class (and as the class a field's value names, x-class-of-value), scalar
                   fields as datatype properties, relations as the property
                   whose `predicate` names them (wb:relatedTo when none does), current claims with their author,
                   quote, source, object and premises
    project(conn)  pgGraph's projection: each content type a node table, wb.relation a node table between them
                   (subject edge both ways, object edge one way, labelled with the predicate), so a path follows
                   relations in their direction; queried as the caller through api.graph_path
"""
from __future__ import annotations

import json

from psycopg import sql

from . import vocab

XSD = {"text": "xsd:string", "bigint": "xsd:integer", "double precision": "xsd:double", "boolean": "xsd:boolean",
       "timestamptz": "xsd:dateTime", "date": "xsd:date", "uuid": "xsd:string"}


def _types(conn) -> list[tuple[str, dict, dict]]:
    """(type id, schema, {column: sql type}) for every content type."""
    out = []
    for type_id, schema in conn.execute("select id, schema from wb.content_type order by id").fetchall():
        cols = dict(conn.execute("select column_name, data_type from information_schema.columns"
                                 " where table_schema = 'content' and table_name = %s", (type_id,)).fetchall())
        cols = {c: ("timestamptz" if t.startswith("timestamp") else t) for c, t in cols.items()}
        out.append((type_id, schema, cols))
    return out


def _lit(text) -> str:
    return json.dumps(str(text), ensure_ascii=False)


def ontology(conn) -> str:
    """wb.term as OWL in Turtle."""
    lines = ["@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .", "@prefix owl: <http://www.w3.org/2002/07/owl#> .", ""]
    relates = vocab.WB + "relatedTo"
    for iri, label, kind, comment, parents, chars, inverse, domain, rng, predicate in conn.execute(
            """select iri, label, kind, comment, parents, characteristics, inverse_of, domain, range, predicate
               from wb.term where kind in ('class', 'property', 'datatype-property') order by kind, iri""").fetchall():
        types = {"class": ["owl:Class"], "property": ["owl:ObjectProperty"], "datatype-property": ["owl:DatatypeProperty"]}[kind]
        types += [{"transitive": "owl:TransitiveProperty", "symmetric": "owl:SymmetricProperty",
                   "functional": "owl:FunctionalProperty"}[c] for c in chars or [] if c in ("transitive", "symmetric", "functional")]
        if kind == "property" and predicate and not parents and iri != relates:
            parents = [relates]
        sub = "rdfs:subClassOf" if kind == "class" else "rdfs:subPropertyOf"
        parts = [f"a {', '.join(types)}"]
        parts += [f"{sub} <{p}>" for p in parents or []]
        parts += [f"owl:inverseOf <{inverse}>"] if inverse else []
        parts += [f"rdfs:domain <{domain}>"] if domain else []
        parts += [f"rdfs:range <{rng}>"] if rng else []
        parts += [f"rdfs:label {_lit(label)}"] if label else []
        parts += [f"rdfs:comment {_lit(comment)}"] if comment else []
        lines.append(f"<{iri}> " + " ;\n    ".join(parts) + " .")
    return "\n".join(lines) + "\n"


def mapping(conn) -> str:
    """The Ontop mapping (native .obda syntax) for every content type, field, relation and current claim."""
    pre = vocab.prefixes(conn.cursor())
    base, wb = vocab.BASE, vocab.WB
    item = lambda t, i: f"<{base}item/{{{t}}}/{{{i}}}>"  # noqa: E731
    out = ["[PrefixDeclaration]", "xsd:\thttp://www.w3.org/2001/XMLSchema#", "rdf:\thttp://www.w3.org/1999/02/22-rdf-syntax-ns#",
           "", "[MappingDeclaration] @collection [["]

    def m(mid, target, source):
        out.extend([f"mappingId\t{mid}", f"target\t\t{target}", f"source\t\t{' '.join(source.split())}", ""])

    for type_id, schema, cols in _types(conn):
        cls = vocab.type_iri(type_id, schema, pre)
        node = f"<{base}item/{type_id}/{{id}}>"
        m(f"type-{type_id}", f"{node} a <{cls}> ; <{wb}slug> {{slug}}^^xsd:string ; <{wb}title> {{title}}^^xsd:string .",
          f"SELECT id, slug, title FROM content.{type_id}")
        for field, prop in (schema.get("properties") or {}).items():
            col = '"' + field.replace('"', '""') + '"'           # a field may be named like a keyword (where, order)
            for value, term in ((prop or {}).get("x-class-of-value") or {}).items():   # a value that names a class
                safe = str(value).replace("'", "''")
                m(f"class-{type_id}-{field}-{value}", f"{node} a <{vocab.expand(term, pre)}> .",
                  f"SELECT id FROM content.{type_id} WHERE {col} = '{safe}'")
            if cols.get(field) in XSD:
                m(f"field-{type_id}-{field}", f"{node} <{vocab.field_iri(type_id, field, prop, pre)}> {{v}}^^{XSD[cols[field]]} .",
                  f"SELECT id, {col} AS v FROM content.{type_id} WHERE {col} IS NOT NULL")
    named = conn.execute("select iri, predicate from wb.term where kind = 'property' and predicate is not null order by predicate").fetchall()
    for iri, predicate in named:
        m(f"rel-{predicate}", f"{item('from_type', 'from_id')} <{iri}> {item('to_type', 'to_id')} .",
          f"SELECT DISTINCT from_type, from_id, to_type, to_id FROM wb.relation WHERE predicate = '{predicate}'")
    unnamed = ", ".join("'" + p.replace("'", "''") + "'" for _, p in named) or "''"
    m("rel-unnamed", f"{item('from_type', 'from_id')} <{wb}relatedTo> {item('to_type', 'to_id')} .",
      f"SELECT DISTINCT from_type, from_id, to_type, to_id FROM wb.relation WHERE predicate NOT IN ({unnamed})")
    claim = f"<{base}claim/{{id}}>"
    m("claim", f"{claim} a <{wb}Claim> ; <{wb}about> {item('subject_type', 'subject_id')} ; <{wb}field> {{field}}^^xsd:string ;"
               f" <{wb}author> {{author}}^^xsd:string .",
      "SELECT id, subject_type, subject_id, field, author FROM wb.claim WHERE status = 'current'")
    m("claim-quote", f"{claim} <{wb}quote> {{quote}}^^xsd:string .",
      "SELECT id, quote FROM wb.claim WHERE status = 'current' AND quote IS NOT NULL")
    m("claim-source", f"{claim} <{wb}sourceUri> {{uri}}^^xsd:string .",
      "SELECT c.id, s.uri FROM wb.claim c JOIN wb.source s ON s.id = c.source_id WHERE c.status = 'current'")
    m("claim-object", f"{claim} <{wb}object> {item('object_type', 'object_id')} .",
      "SELECT id, object_type, object_id FROM wb.claim WHERE status = 'current' AND object_id IS NOT NULL")
    m("claim-premise", f"{claim} <{wb}premise> <{base}claim/{{premise}}> .",
      "SELECT c.id, p.premise FROM wb.claim c, jsonb_array_elements_text(c.span -> 'premises') AS p(premise)"
      " WHERE c.status = 'current' AND jsonb_typeof(c.span -> 'premises') = 'array'")
    out.append("]]")
    return "\n".join(out) + "\n"


def project(conn) -> dict:
    """pgGraph's projection, registered afresh from the content types and built (it then follows writes by trigger)."""
    if not conn.execute("select 1 from pg_extension where extname = 'graph'").fetchone():
        return {"skipped": "pgGraph is not installed in this database"}
    conn.execute("select graph.reset(true)")
    rel = sql.Literal("wb.relation")
    conn.execute(sql.SQL("select graph.add_table({}::regclass, 'id', array['predicate', 'author'])").format(rel))
    types = [t for t, _, _ in _types(conn)]
    for t in types:
        node = sql.Literal(f"content.{t}")
        conn.execute(sql.SQL("select graph.add_table({}::regclass, 'id', array['slug', 'title'])").format(node))
        conn.execute(sql.SQL("select graph.add_edge({}::regclass, 'from_id', {}::regclass, 'id', 'subject', true)").format(rel, node))
        conn.execute(sql.SQL("select graph.add_edge({}::regclass, 'to_id', {}::regclass, 'id', 'object', false, null, 'predicate')").format(rel, node))
    conn.commit()                    # pgGraph builds outside the transaction that registered its sources
    nodes, edges = conn.execute("select nodes_loaded, edges_loaded from graph.build()").fetchone()
    conn.execute("select * from graph.grant_graph('default', 'wb_viewer', 'read')")    # readers query it as themselves
    conn.commit()
    return {"node_tables": len(types) + 1, "nodes": nodes, "edges": edges}
