#!/usr/bin/env python3
"""Generate substrate's vocabulary (spec step 7): vocabulary.yaml, and `x-term` on every content type and field in
types/*.json, from what the plugin already has:

  - each content type is a class (its title, PascalCase), each field a datatype property (camelCase);
  - each kind of map entry (the component type's kinds) is a class under sub:Entity, and the component type's `kind`
    field says which (x-class-of-value);
  - each relation predicate substrate's extractors state (ctx.relate in substrate_plugin.py, and the catalog's
    RELATIONS) is an object property;
  - vocabulary.axioms.yaml says how they relate (parents, transitive, inverses), the only hand-written part.

    python3 plugins/substrate/vocab.py [--check]     # --check: fail if the files are not what it would write
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
NS = "https://substrate.local/ns#"


def pascal(text: str) -> str:
    return "".join(w[:1].upper() + w[1:] for w in re.split(r"[^A-Za-z0-9]+", text) if w)


def camel(text: str) -> str:
    p = pascal(text)
    return p[:1].lower() + p[1:]


def predicates() -> list[str]:
    src = (HERE / "substrate_plugin.py").read_text()
    found = set(re.findall(r'ctx\.relate\([^,]+,\s*[^,]+,\s*"([A-Za-z]+)"', src))
    rel = re.search(r"RELATIONS = \{(.*?)\}", src, re.S)
    found |= set(re.findall(r':\s*"([A-Za-z]+)"', rel.group(1))) if rel else set()
    return sorted(found)


def catalog_kinds() -> list[str]:
    """The map's entity kinds, as the component type names them (its kind field's x-class-of-value)."""
    kind = json.loads((HERE / "types/component.json").read_text())["properties"]["kind"]
    return sorted(kind.get("x-class-of-value") or {})


def generate() -> tuple[dict, dict[Path, dict]]:
    axioms = yaml.safe_load((HERE / "vocabulary.axioms.yaml").read_text())
    kinds = catalog_kinds()
    terms, schemas = [], {}
    classes = dict(axioms.get("classes") or {})
    observed = set(axioms.get("observed") or [])
    fields: dict[str, list[tuple[str, dict]]] = {}
    renamed = axioms.get("field_terms") or {}          # "type.field": a term's local name, where camelCase would clash
    for f in sorted((HERE / "types").glob("*.json")):
        schema = json.loads(f.read_text())
        name = pascal(schema.get("title") or f.stem)
        if name in kinds:                                   # a served API is not the catalog's API kind
            name = "Observed" + name
        cls = "Entity" if f.stem == "component" else name
        schema["x-term"] = f"sub:{cls}"
        parent = "sub:Observed" if pascal(schema.get("title") or f.stem) in observed else "wb:Item"
        classes.setdefault(cls, {"parents": [parent]})
        classes[cls].setdefault("label", schema.get("title"))
        classes[cls].setdefault("comment", schema.get("description"))
        for field, prop in (schema.get("properties") or {}).items():
            local = renamed.get(f"{f.stem}.{field}", camel(field))
            prop["x-term"] = f"sub:{local}"
            fields.setdefault(local, []).append((cls, prop))
        if f.stem == "component":
            schema["properties"]["kind"]["x-class-of-value"] = {k: f"sub:{k}" for k in kinds}
        schemas[f] = schema
    for k in kinds:
        classes.setdefault(k, {"parents": ["sub:Entity"], "comment": f"A catalog entity of kind {k} (Backstage's entity model)."})
    for name, c in sorted(classes.items()):
        terms.append({"iri": f"sub:{name}", "kind": "class", "label": c.get("label") or name,
                      **{k: v for k, v in c.items() if k in ("parents", "comment") and v}})
    for name, uses in sorted(fields.items()):
        t = {"iri": f"sub:{name}", "kind": "datatype-property", "label": name}
        if len({cls for cls, _ in uses}) == 1:
            t["domain"] = f"sub:{uses[0][0]}"
        desc = next((p.get("description") for _, p in uses if p.get("description")), None)
        if desc and len(uses) == 1:
            t["comment"] = desc
        terms.append(t)
    props = dict(axioms.get("properties") or {})
    for p in predicates():
        props.setdefault(p, {"parents": ["wb:relatedTo"]})
    clash = sorted(set(fields) & set(props))
    if clash:
        raise SystemExit(f"a field and a relation would share a term ({', '.join(clash)}): name the field's term in "
                         "vocabulary.axioms.yaml's field_terms (\"type.field\": localName)")
    for name, p in sorted(props.items()):
        t = {"iri": f"sub:{name}", "kind": "property", "label": name}
        t["predicate"] = name               # stated by an extractor, or drawn by substrate:reasoner (e.g. reaches)
        t.update({k: v for k, v in p.items() if k in ("parents", "characteristics", "inverse_of", "comment", "domain", "range") and v})
        terms.append(t)
    vocabulary = {"vocabulary": "substrate", "prefixes": {"sub": NS}, "terms": terms}
    return vocabulary, schemas


HEADER = ("# Generated by plugins/substrate/vocab.py from types/*.json, the map's kinds, the relations substrate's\n"
          "# extractors state, and vocabulary.axioms.yaml (the hand-written part). Edit those and run it again; never this.\n")


def main(check: bool) -> int:
    vocabulary, schemas = generate()
    want = {HERE / "vocabulary.yaml": HEADER + yaml.safe_dump(vocabulary, sort_keys=False, allow_unicode=True, width=120)}
    want.update({f: json.dumps(s, indent=2, ensure_ascii=False) + "\n" for f, s in schemas.items()})
    stale = [f for f, text in want.items() if not f.is_file() or f.read_text() != text]
    if check:
        for f in stale:
            print(f"out of date: {f.relative_to(ROOT)} (run python3 plugins/substrate/vocab.py)")
        return 1 if stale else 0
    for f in stale:
        f.write_text(want[f])
    print(f"{len(vocabulary['terms'])} terms; {len(stale)} files written")
    return 0


if __name__ == "__main__":
    sys.exit(main("--check" in sys.argv))
