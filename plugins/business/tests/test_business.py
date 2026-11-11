"""The business plugin (README.md, "Check") in throwaway databases:
- every type names its class from a picked model, the terms are loaded, and the SSSOM mappings with them
- the demo business's map imports as items, exports to the same map, and re-imports changing nothing; into a
  second, empty Workbench it makes the same entities, and their export is the same file
- the demo BPMN process imports as a process, activities, roles and documents, and exports to BPMN 2.0 XML with
  the same elements, flows, lanes, data and diagram; the export re-imports to the same items
- a process mapped without a diagram exports with one laid out, every flow node drawn
- a domain's import leaves another domain alone

    WORKBENCH_ADMIN_URL=postgresql://postgres:...@127.0.0.1:5432/postgres python3 plugins/business/tests/test_business.py
"""
import json
import os
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
PLUGIN = ROOT / "plugins/business"
sys.path[:0] = [str(ROOT / "workbench"), str(PLUGIN)]
os.environ.setdefault("WORKBENCH_JWT_SECRET", "b-" + "q" * 40)

import psycopg  # noqa: E402
from psycopg import sql  # noqa: E402

from workbench import cli  # noqa: E402
from workbench.extract import Plugins, run_extractor  # noqa: E402

import business_plugin as bp  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print(("ok  " if ok else "FAIL"), name, "" if ok else str(detail)[:1500])


DEMO = PLUGIN / "demo/harbour-bakery.yaml"
BPMN = PLUGIN / "demo/wholesale-order.bpmn"
DBS = [f"workbench_test_{os.getpid()}_{n}" for n in ("a", "b")]


def use(db):
    os.environ["WORKBENCH_DB"] = db
    cli.migrate()
    cli.load_plugin(PLUGIN)
    plugins = Plugins().load(ROOT / "plugins")
    return plugins


def extract(plugins, name, **inputs):
    r = run_extractor(cli.connect, plugins, f"business:{name}", inputs)
    if not r.get("ok"):
        raise RuntimeError(r)
    return r


def norm(doc):
    """A map file as sets: lists inside relations are order-free."""
    out = {}
    for t, items in (doc.get("items") or {}).items():
        for name, body in (items or {}).items():
            b = {}
            for k, v in (body or {}).items():
                b[k] = sorted([v] if isinstance(v, str) else v) if k in bp.PREDICATES else v
            b.setdefault("title", name)
            out[(t, name)] = b
    return out


def snapshot(conn):
    """Every business item's id, slug and updated_at, and the claim count: what a no-op import must not change."""
    rows = {}
    for t in bp.TYPES:
        for i, s, u in conn.execute(f'select id::text, slug, updated_at from api."{t}"').fetchall():
            rows[(t, s)] = (i, u)
    claims = conn.execute("select count(*) from wb.claim").fetchone()[0]
    return rows, claims


def bpmn_facts(xml: str):
    root = ET.fromstring(xml)
    ns = bp.NS
    proc = root.find("bpmn:process", ns)
    nodes = {(el.get("id"), el.tag.split("}")[-1], el.get("name")) for el in proc if el.tag.split("}")[-1] in bp.FLOW_NODES}
    flows = set()
    for f in proc.findall("bpmn:sequenceFlow", ns):
        c = f.find("bpmn:conditionExpression", ns)
        flows.add((f.get("id"), f.get("sourceRef"), f.get("targetRef"), f.get("name"), c.text if c is not None else None))
    lanes = {(lane.get("id"), lane.get("name"), frozenset(r.text for r in lane.findall("bpmn:flowNodeRef", ns)))
             for lane in proc.iter(bp.q("lane"))}
    data = {(r.get("id"), r.get("name"), r.get("dataObjectRef")) for r in proc.findall("bpmn:dataObjectReference", ns)}
    assoc = set()
    for el in proc:
        for a in el.findall("bpmn:dataInputAssociation", ns):
            assoc.add((el.get("id"), "in", a.get("id"), a.find("bpmn:sourceRef", ns).text))
        for a in el.findall("bpmn:dataOutputAssociation", ns):
            assoc.add((el.get("id"), "out", a.get("id"), a.find("bpmn:targetRef", ns).text))
    shapes = {s.get("bpmnElement"): tuple(float(s.find("dc:Bounds", ns).get(k)) for k in ("x", "y", "width", "height"))
              for s in root.iter(bp.q("BPMNShape", "bpmndi"))}
    edges = {e.get("bpmnElement"): tuple((float(w.get("x")), float(w.get("y"))) for w in e.findall("di:waypoint", ns))
             for e in root.iter(bp.q("BPMNEdge", "bpmndi"))}
    defaults = {el.get("id"): el.get("default") for el in proc if el.get("default")}
    eventdefs = {(el.get("id"), c.tag.split("}")[-1]) for el in proc for c in el if c.tag.split("}")[-1] in bp.EVENT_DEFS}
    return {"nodes": nodes, "flows": flows, "lanes": lanes, "data": data, "assoc": assoc, "shapes": shapes, "edges": edges,
            "defaults": defaults, "eventdefs": eventdefs, "participant": [p.get("name") for p in root.iter(bp.q("participant"))]}


named_user = [str(f.relative_to(PLUGIN)) for f in PLUGIN.rglob("*") if f.is_file() and "__pycache__" not in f.parts
              and f.suffix in (".py", ".md", ".yaml", ".json", ".tsv", ".bpmn") and ("sub" + "strate") in f.read_text().lower()]
check("nothing in the plugin names the system that uses it", not named_user, named_user)

try:
    plugins = use(DBS[0])
    with cli.connect() as conn:
        # ---- the terms
        terms = {r[0]: r[1] for r in conn.execute("select iri, vocabulary from wb.term").fetchall()}
        named = {}
        for t in bp.TYPES:
            schema = conn.execute("select schema from wb.content_type where id = %s", (t,)).fetchone()[0]
            named[t] = schema.get("x-term")
        pre = yaml.safe_load((PLUGIN / "vocabulary.yaml").read_text())["prefixes"]
        missing = [t for t, x in named.items() if not x or not x.split(":")[0] in pre or pre[x.split(":")[0]] + x.split(":")[1] not in terms]
        check("every business type names its class from a picked model, and the term is loaded", not missing, missing)
        minted = [t for t, x in named.items() if x.startswith("biz:")]
        check("no type's class is minted here", not minted, minted)
        n_map = conn.execute("select count(*) from wb.mapping where plugin = 'business'").fetchone()[0]
        rows = sum(1 for ln in (PLUGIN / "mappings.sssom.tsv").read_text().splitlines() if ln and not ln.startswith("#")) - 1
        check("the SSSOM mappings are loaded, every row", n_map == rows and rows >= 12, (n_map, rows))
        unmapped = [t for t, x in named.items() if not conn.execute(
            "select 1 from wb.mapping where subject_id = %s", (pre[x.split(':')[0]] + x.split(':')[1],)).fetchone()]
        check("every type's term is mapped to another model's", not unmapped, unmapped)
        iri = conn.execute("select object_id from wb.mapping where subject_id = 'http://www.w3.org/ns/org#Organization' "
                           "and predicate_id = 'http://www.w3.org/2004/02/skos/core#exactMatch'").fetchone()
        check("mappings are stored as IRIs (CURIEs expanded)", iri and iri[0] == "https://schema.org/Organization", iri)
    cli.load_plugin(PLUGIN)
    with cli.connect() as conn:
        check("loading the plugin again leaves the same mappings",
              conn.execute("select count(*) from wb.mapping where plugin = 'business'").fetchone()[0] == n_map)

    # ---- the map round trip
    extract(plugins, "map", file=str(DEMO))
    with cli.connect() as conn:
        out1 = bp.export_map(conn, "harbour-bakery")
        before = snapshot(conn)
        n_items = len(before[0])
    src = yaml.safe_load(DEMO.read_text())
    got = yaml.safe_load(out1)
    check("the demo map imports as items", n_items == len(norm(src)), (n_items, len(norm(src))))
    diff = {k: (norm(src).get(k), norm(got).get(k)) for k in set(norm(src)) | set(norm(got)) if norm(src).get(k) != norm(got).get(k)}
    check("and exports to the same map", not diff, diff)
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(out1)
        exported = f.name
    extract(plugins, "map", file=exported)
    with cli.connect() as conn:
        after = snapshot(conn)
        out2 = bp.export_map(conn, "harbour-bakery")
    check("re-importing the export changes nothing (same ids, no new claims)", after == before,
          (len(after[0]), len(before[0]), after[1], before[1]))
    check("and exports the same file again", out2 == out1)

    # ---- another domain beside it
    other = {"domain": "corner-shop", "items": {"organisation": {"corner-shop": {"title": "Corner Shop"}},
                                                  "role": {"shopkeeper": {"roleIn": "corner-shop"}}}}
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        yaml.safe_dump(other, f)
        other_file = f.name
    extract(plugins, "map", file=other_file)
    with cli.connect() as conn:
        out3 = bp.export_map(conn, "harbour-bakery")
        live = conn.execute("select count(*) from api.role where wb.live(id)").fetchone()[0]
    check("a second domain's import leaves the first alone", out3 == out1)
    check("and both domains' items stand", live == len(src["items"]["role"]) + 1, live)

    # ---- the BPMN round trip
    extract(plugins, "bpmn", file=str(BPMN), domain="harbour-bakery")
    with cli.connect() as conn:
        x1 = bp.export_bpmn(conn, "harbour-bakery.wholesale-order")
        acts = conn.execute("select count(*) from api.activity where starts_with(slug, 'harbour-bakery.wholesale-order.')").fetchone()[0]
        lane_roles = conn.execute("""select count(distinct r.to_id) from wb.relation r join api.activity a on a.id = r.from_id
                                      where r.predicate = 'performedBy' and starts_with(a.slug, 'harbour-bakery.wholesale-order.')""").fetchone()[0]
        roles = conn.execute("select count(*) from api.role where domain = 'harbour-bakery'").fetchone()[0]
    orig, back = bpmn_facts(BPMN.read_text()), bpmn_facts(x1)
    check("the BPMN process imports: a flow node is an activity", acts == len(orig["nodes"]), (acts, len(orig["nodes"])))
    check("its lanes are the map's roles, not new ones", lane_roles == 3 and roles == len(src["items"]["role"]), (lane_roles, roles))
    for k in orig:
        check(f"the export has the same {k}", orig[k] == back[k], {"only in the file": sorted(map(str, set(orig[k]) - set(back[k]))) if isinstance(orig[k], (set, dict)) else orig[k],
                                                                   "only in the export": sorted(map(str, set(back[k]) - set(orig[k]))) if isinstance(back[k], (set, dict)) else back[k]})
    with tempfile.NamedTemporaryFile("w", suffix=".bpmn", delete=False) as f:
        f.write(x1)
        bfile = f.name
    with cli.connect() as conn:
        before = snapshot(conn)
    extract(plugins, "bpmn", file=bfile, domain="harbour-bakery")
    with cli.connect() as conn:
        after = snapshot(conn)
        x2 = bp.export_bpmn(conn, "harbour-bakery.wholesale-order")
    check("re-importing the exported BPMN changes no item", after[0] == before[0])
    check("and exports the same XML", x2 == x1)

    # ---- a process mapped without a diagram
    with cli.connect() as conn:
        x3 = bp.export_bpmn(conn, "harbour-bakery.invoicing")
    f3 = bpmn_facts(x3)
    drawn = {n for n, *_ in f3["nodes"]} <= set(f3["shapes"]) and {fid for fid, *_ in f3["flows"]} <= set(f3["edges"])
    check("a mapped process exports to BPMN with every node and flow drawn", drawn and len(f3["nodes"]) == 4, f3)
    check("its lanes are absent and its flows follow the map", len(f3["flows"]) == 3, f3["flows"])

    # ---- a second, empty Workbench
    plugins_b = use(DBS[1])
    exp = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
    exp.write(out1)
    exp.close()
    extract(plugins_b, "map", file=exp.name)
    with cli.connect() as conn:
        out_b = bp.export_map(conn, "harbour-bakery")
    check("the export, imported into an empty Workbench, makes the same entities and the same file", out_b == out1)
finally:
    with psycopg.connect(cli.url("postgres"), autocommit=True) as conn:
        for db in DBS:
            conn.execute(sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(db)))

print(f"{sum(checks)}/{len(checks)} checks passed")
sys.exit(0 if all(checks) else 1)
