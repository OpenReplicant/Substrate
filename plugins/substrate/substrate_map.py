"""A system's map between Workbench and Backstage's entity model (MAP.md).

Workbench holds the map: one component item per entity, each spec field a column, every value a claim. This module
is the translation both ways, and nothing else: `substrate:catalog` imports a file through `doc_fields`, and
`export` writes the entities of one domain back as a catalog file, in a stable order, so the export of an unchanged
map is byte-for-byte the same. Morphogen reads that file from the base commit as its rules (its structure check
and gate), which is why the map's export is committed for a system whose judge is Morphogen.

    python3 plugins/substrate/substrate_map.py export [DOMAIN] [FILE]   # needs WORKBENCH_ADMIN_URL (scripts/map.sh)
    python3 plugins/substrate/substrate_map.py check [DOMAIN] [FILE]    # exit 1 when FILE differs from the map
    python3 plugins/substrate/substrate_map.py count [DOMAIN]           # how many entities stand in it
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

NODE_KINDS = {"component", "resource", "airesource"}
# spec keys and the component fields that hold them, in the order an exported entry lists them
SPEC_FIELDS = {"type": "type", "lifecycle": "lifecycle", "owner": "owner", "system": "system", "domain": "domain",
               "subcomponentOf": "subcomponent_of", "dependsOn": "depends_on", "providesApis": "provides_apis",
               "consumesApis": "consumes_apis", "definition": "definition", "children": "children"}
KIND_ORDER = ["Group", "Domain", "System", "Component", "Resource", "AiResource", "API"]
API_VERSION = {"AiResource": "backstage.io/v1alpha1"}
HEADER = """# {domain}'s map, in Backstage's catalog entity model. Generated from Workbench by `scripts/map.sh export`:
# edit the map in Workbench (its shell, or MCP's save_item and retire_item), not here. Morphogen reads this file
# from the base commit as its rules (morphogen.yaml), and a new machine's first `scripts/up.sh` imports it.
# What each annotation means: plugins/substrate/MAP.md.
"""


def slug_for(kind: str, name: str) -> str:
    """Components, resources and AI resources keep their name (so a skill's entry and the skill meet); other
    kinds are prefixed, since a system and a component may share a name."""
    return name if kind.lower() in NODE_KINDS else f"{kind.lower()}-{name}"


def name_for(kind: str, slug: str) -> str:
    prefix = f"{kind.lower()}-"
    return slug if kind.lower() in NODE_KINDS or not slug.startswith(prefix) else slug[len(prefix):]


def doc_fields(doc: dict) -> dict:
    """A catalog entity's component fields (None where it says nothing)."""
    md, spec = doc.get("metadata") or {}, doc.get("spec") or {}
    out = {"kind": str(doc.get("kind", "")), "description": md.get("description"), "annotations": md.get("annotations")}
    out.update({f: spec.get(k) for k, f in SPEC_FIELDS.items()})
    return out


def domain_slugs(conn, domain: str) -> list[str]:
    """Every live entity in a domain: the domain, its systems, what they hold, and the groups any of them names."""
    rows = conn.execute("""select slug, kind, system, domain, owner from api.component c where wb.live(c.id)""").fetchall()
    systems = {s for s, k, _, d, _ in rows if k == "System" and d == domain}
    names = {name_for("System", s) for s in systems}
    keep = {s for s, k, sysname, _, _ in rows if k not in ("Domain", "System", "Group") and sysname in names}
    keep |= systems | {s for s, k, *_ in rows if k == "Domain" and name_for("Domain", s) == domain}
    owners = {o.split(":")[-1].split("/")[-1] for s, k, _, _, o in rows if s in keep and o}
    keep |= {s for s, k, *_ in rows if k == "Group" and name_for("Group", s) in owners}
    return sorted(keep)


def entities(conn, domain: str) -> list[dict]:
    cols = ["slug", "title", *dict.fromkeys(["kind", "description", "annotations", *SPEC_FIELDS.values()])]
    slugs = domain_slugs(conn, domain)
    rows = conn.execute(f"select {', '.join(cols)} from api.component where slug = any(%s)", (slugs,)).fetchall()
    docs = []
    for row in rows:
        r = dict(zip(cols, row))
        name = name_for(r["kind"], r["slug"])
        md = {"name": name}
        if r["title"] and r["title"] != name:
            md["title"] = r["title"]
        if r["description"] is not None:
            md["description"] = r["description"]
        if r["annotations"]:
            md["annotations"] = {k: r["annotations"][k] for k in sorted(r["annotations"])}
        spec = {k: r[f] for k, f in SPEC_FIELDS.items() if r[f] is not None}
        docs.append({"apiVersion": API_VERSION.get(r["kind"], "backstage.io/v1alpha1"), "kind": r["kind"],
                     "metadata": md, "spec": spec})
    rank = {k: i for i, k in enumerate(KIND_ORDER)}
    docs.sort(key=lambda d: (rank.get(d["kind"], len(rank)), d["spec"].get("system") or "", d["metadata"]["name"]))
    return docs


def dump(docs: list[dict], domain: str) -> str:
    body = yaml.safe_dump_all(docs, sort_keys=False, allow_unicode=True, width=120, explicit_start=True)
    return HEADER.format(domain=domain) + body


def normalized(docs) -> dict:
    """{(kind, name): the entity without key order, empty values, or a title equal to its name}: what two files must
    agree on to describe the same map."""
    out = {}
    for d in docs:
        if not d or str(d.get("kind")) == "Location":
            continue
        md, spec = dict(d.get("metadata") or {}), {k: v for k, v in (d.get("spec") or {}).items() if v is not None}
        if md.get("title") == md.get("name"):
            md.pop("title")
        out[(str(d["kind"]), md["name"])] = {"metadata": {k: v for k, v in md.items() if v not in (None, {})}, "spec": spec}
    return out


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else ""
    domain = argv[1] if len(argv) > 1 else "substrate"
    root = Path(os.environ.get("WB_SUBSTRATE_ROOT") or Path(__file__).resolve().parents[2])
    target = root / (argv[2] if len(argv) > 2 else "catalog-info.yaml")
    sys.path.insert(0, str(root / "workbench"))
    from workbench import cli
    with cli.connect() as conn:
        docs = entities(conn, domain)
    if cmd == "count":
        print(len(docs))
        return 0
    if not docs:
        print(f"no live entities in domain {domain}")
        return 1
    text = dump(docs, domain)
    if cmd == "export":
        target.write_text(text)
        print(f"wrote {target.relative_to(root) if target.is_relative_to(root) else target}: {len(docs)} entities of {domain}")
        return 0
    if cmd == "check":
        if not target.exists():
            print(f"{target.name} is missing: scripts/map.sh export")
            return 1
        same = normalized(yaml.safe_load_all(target.read_text())) == normalized(yaml.safe_load_all(text))
        print(f"{target.name} matches the map in Workbench" if same else
              f"the map in Workbench differs from {target.name}: scripts/map.sh export, then commit it")
        return 0 if same else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
