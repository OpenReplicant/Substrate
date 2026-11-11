"""Workbench's business plugin (README.md): a business's map and its BPMN 2.0 processes, in and out.

business:map    a business's map file (YAML: its domain, its items by type, their relations) written as items
business:bpmn   a BPMN 2.0 XML file's processes written as items: the process, its flow nodes as activities, its
                lanes as roles, its data objects as documents, and the diagram's shapes kept for writing it back

Exports read Workbench and write the same formats back (export_map, export_bpmn), so a map or a process makes the
round trip; run them with `python3 business_plugin.py export-map DOMAIN` or `export-bpmn PROCESS-SLUG`.
"""
from __future__ import annotations

import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
TYPES = ("organisation", "unit", "role", "person", "resource", "process", "activity", "event", "decision", "document",
         "measure", "goal")
# relation predicates a map file may state, read from the vocabulary (a property with a `predicate`)
PREDICATES = sorted(t["predicate"] for t in yaml.safe_load((HERE / "vocabulary.yaml").read_text())["terms"]
                    if t.get("predicate"))

NS = {"bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL", "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
      "dc": "http://www.omg.org/spec/DD/20100524/DC", "di": "http://www.omg.org/spec/DD/20100524/DI",
      "xsi": "http://www.w3.org/2001/XMLSchema-instance"}
FLOW_NODES = ("task", "userTask", "serviceTask", "manualTask", "businessRuleTask", "sendTask", "receiveTask", "scriptTask",
              "callActivity", "subProcess", "startEvent", "endEvent", "intermediateCatchEvent", "intermediateThrowEvent",
              "boundaryEvent", "exclusiveGateway", "parallelGateway", "inclusiveGateway", "eventBasedGateway",
              "complexGateway")
EVENT_DEFS = ("messageEventDefinition", "timerEventDefinition", "signalEventDefinition", "errorEventDefinition",
              "conditionalEventDefinition", "escalationEventDefinition", "terminateEventDefinition",
              "compensateEventDefinition", "linkEventDefinition", "cancelEventDefinition")
SIZES = {"task": (100, 80), "event": (36, 36), "gateway": (50, 50)}


def slugify(text: str) -> str:
    t = re.sub(r"[^a-z0-9]+", "-", re.sub(r"['\u2019]", "", str(text).lower())).strip("-")
    return t[:120] or "x"


def q(tag: str, ns: str = "bpmn") -> str:
    return f"{{{NS[ns]}}}{tag}"


def size_of(kind: str) -> tuple[int, int]:
    return SIZES["event" if kind.endswith("Event") else "gateway" if kind.endswith("Gateway") else "task"]


# ---- reading Workbench

def live_items(conn, type_id: str, domain: str) -> list[dict]:
    rows = conn.execute(f'select to_jsonb(x) from api."{type_id}" x where domain = %s and wb.live(x.id) order by slug',
                        (domain,)).fetchall()
    return [r[0] for r in rows]


def relations_from(conn, ids: list[str]) -> list[tuple]:
    return conn.execute("""select r.from_id::text, r.predicate, r.to_type, r.to_id::text from wb.relation r
                            where r.from_id = any(%s::uuid[]) and wb.live(r.to_id)
                            order by r.predicate, r.to_id""", (ids,)).fetchall()


def fields_of(conn, type_id: str) -> list[str]:
    schema = conn.execute("select schema from wb.content_type where id = %s", (type_id,)).fetchone()[0]
    return [k for k in (schema.get("properties") or {}) if k != "domain"]


def local(slug: str, domain: str) -> str:
    return slug[len(domain) + 1:] if slug.startswith(domain + ".") else slug


def done_in(ctx, type_id: str, keep: set[str]):
    """Retract this extractor's claims on items of the type it no longer states, among `keep`'s complement within
    one scope: ctx.done would retract across every domain, so the items outside the scope are counted as seen."""
    mine = set(ctx.seen.get(type_id, set()))
    ctx.seen[type_id] = mine | keep
    try:
        ctx.done(type_id)
    finally:
        ctx.seen[type_id] = mine        # the run's relations are replaced only on the items it read


# ---- the map file

def register(wb):
    root = Path(wb.setting("root") or os.getcwd())

    def read(inputs) -> tuple[Path, bytes]:
        path = Path(inputs["file"])
        path = path if path.is_absolute() else root / path
        return path, path.read_bytes()

    def map_(ctx, inputs):
        path, data = read(inputs)
        src = ctx.source(f"file:{inputs.get('uri') or path.name}", data, "application/yaml")
        doc = yaml.safe_load(data) or {}
        domain = doc.get("domain")
        if not domain or slugify(domain) != domain:
            raise ValueError("a map file names its domain: lowercase letters, digits and -")
        items = doc.get("items") or {}
        unknown = sorted(set(items) - set(TYPES))
        if unknown:
            raise ValueError(f"no business type {', '.join(unknown)} (types: {', '.join(TYPES)})")
        where: dict[str, tuple[str, str]] = {}           # local slug -> (type, id)
        pending = []
        for type_id in TYPES:
            known = set(fields_of(ctx.conn, type_id))
            for name, body in sorted((items.get(type_id) or {}).items()):
                body = body or {}
                if name in where:
                    raise ValueError(f"{name!r} is named twice in the map: a local name is one item across the types")
                extra = sorted(k for k in body if k not in known and k not in PREDICATES and k != "title")
                if extra:
                    raise ValueError(f"{type_id} {name}: {', '.join(extra)} is neither a field nor a relation")
                fields = {k: v for k, v in body.items() if k in known}
                iid = ctx.upsert(type_id, f"{domain}.{name}", {**fields, "domain": domain},
                                 title=body.get("title") or name, source=src)
                where[name] = (type_id, iid)
                pending += [(type_id, iid, p, body[p]) for p in PREDICATES if p in body]
        for type_id, iid, pred, targets in pending:
            for t in [targets] if isinstance(targets, str) else targets:
                if t not in where:
                    raise ValueError(f"{pred} names {t!r}, which the map does not have")
                ctx.relate(type_id, iid, pred, where[t][0], where[t][1], source=src)
        for type_id in TYPES:
            others = {str(r[0]) for r in ctx.conn.execute(
                f'select id from api."{type_id}" where domain is distinct from %s', (domain,)).fetchall()}
            done_in(ctx, type_id, others)
        ctx.log(f"{domain}: {len(where)} items, {sum(len([t] if isinstance(t, str) else t) for *_, t in pending)} relations")

    def bpmn(ctx, inputs):
        path, data = read(inputs)
        src = ctx.source(f"file:{inputs.get('uri') or path.name}", data, "application/xml")
        domain = inputs.get("domain")
        if not domain:
            raise ValueError("--input domain=NAME: the business the process belongs to")
        result = read_bpmn(data)
        for w in result["warnings"]:
            ctx.log(w)
        for proc in result["processes"]:
            pslug = f"{domain}.{proc['local']}"
            roles, docs = {}, {}
            for lane in proc["lanes"]:
                if lane["name"]:
                    rs = f"{domain}.{slugify(lane['name'])}"
                    roles[lane["id"]] = ctx.upsert("role", rs, {"domain": domain}, title=lane["name"], source=src)
                    lane["role"] = local(rs, domain)
                    for kept in proc["bpmn"]["lanes"]:
                        if kept["id"] == lane["id"]:
                            kept["role"] = lane["role"]
            for ref in proc["data"]:
                ds = f"{domain}.{slugify(ref['name'] or ref['id'])}"
                docs[ref["id"]] = (ctx.upsert("document", ds, {"domain": domain}, title=ref["name"] or ref["id"], source=src),
                                   local(ds, domain))
                ref["document"] = docs[ref["id"]][1]
            node_slug = {n["id"]: f"{pslug}.{slugify(n['id'])}" for n in proc["nodes"]}
            for n in proc["nodes"]:
                for f in n["outgoing"]:
                    f["to"] = local(node_slug[f.pop("target")], domain)
                for a in n["data"]:
                    a["document"] = docs[a["ref"]][1] if a["ref"] in docs else None
            pid = ctx.upsert("process", pslug, {"domain": domain, "bpmn": proc["bpmn"]}, title=proc["name"] or proc["id"],
                             source=src)
            seen = set()
            for n in proc["nodes"]:
                aid = ctx.upsert("activity", node_slug[n["id"]],
                                 {"domain": domain, "kind": n["kind"], "bpmn_id": n["id"], "shape": n["shape"],
                                  "outgoing": n["outgoing"], "data": n["data"], "bpmn": n["bpmn"] or None},
                                 title=n["name"] or n["id"], source=src)
                seen.add(aid)
                ctx.relate("activity", aid, "partOf", "process", pid, source=src)
                for lane in proc["lanes"]:
                    if n["id"] in lane["nodes"] and lane["id"] in roles:
                        ctx.relate("activity", aid, "performedBy", "role", roles[lane["id"]], source=src)
                for a in n["data"]:
                    if a["ref"] in docs:
                        ctx.relate("activity", aid, "uses" if a["direction"] == "in" else "produces", "document",
                                   docs[a["ref"]][0], source=src)
            # flows are related once every activity of the process exists
            ids = {node_slug[n["id"]]: None for n in proc["nodes"]}
            for row in ctx.conn.execute("select slug, id::text from api.activity where slug = any(%s)", (list(ids),)).fetchall():
                ids[row[0]] = row[1]
            for n in proc["nodes"]:
                for f in n["outgoing"]:
                    ctx.relate("activity", ids[node_slug[n["id"]]], "flowsTo", "activity", ids[f"{domain}.{f['to']}"], source=src)
            others = {str(r[0]) for r in ctx.conn.execute(
                "select id from api.activity where not starts_with(slug, %s)", (pslug + ".",)).fetchall()}
            done_in(ctx, "activity", others | seen)
            ctx.log(f"{pslug}: {len(proc['nodes'])} activities, {len(proc['lanes'])} lanes, {len(proc['data'])} data objects")

    wb.extractor("map", map_, "a business's map file (--input file=PATH): its domain's items and relations",
                 {"file": "path to the map's YAML"})
    wb.extractor("bpmn", bpmn, "a BPMN 2.0 XML file's processes as items (--input file=PATH --input domain=NAME)",
                 {"file": "path to the .bpmn file", "domain": "the business it belongs to"})


# ---- BPMN 2.0 XML in

def bounds(el) -> dict | None:
    b = el.find("dc:Bounds", NS) if el is not None else None
    return None if b is None else {k: round(float(b.get(k)), 2) for k in ("x", "y", "width", "height")}


def waypoints(el) -> list:
    return [[round(float(w.get("x")), 2), round(float(w.get("y")), 2)] for w in el.findall("di:waypoint", NS)] if el is not None else []


def read_bpmn(data: bytes) -> dict:
    """The processes in a BPMN 2.0 XML file, in the subset this plugin keeps: flow nodes, sequence flows, lanes, data
    object references and their associations, a participant per process, and their diagram (shapes and edges)."""
    root = ET.fromstring(data)
    if root.tag != q("definitions"):
        raise ValueError("not a BPMN 2.0 file: its root is not bpmn:definitions")
    warnings = []
    shapes = {s.get("bpmnElement"): s for s in root.iter(q("BPMNShape", "bpmndi"))}
    edges = {e.get("bpmnElement"): e for e in root.iter(q("BPMNEdge", "bpmndi"))}
    diagram = root.find("bpmndi:BPMNDiagram", NS)
    plane = diagram.find("bpmndi:BPMNPlane", NS) if diagram is not None else None
    collab = root.find("bpmn:collaboration", NS)
    participants = {p.get("processRef"): p for p in collab.findall("bpmn:participant", NS)} if collab is not None else {}

    def shape(el_id):
        s = shapes.get(el_id)
        b = bounds(s)
        if b is not None:
            b["di"] = s.get("id")
            if s.get("isHorizontal") is not None:
                b["horizontal"] = s.get("isHorizontal") == "true"
        return b

    out = []
    for p in root.findall("bpmn:process", NS):
        known = set(FLOW_NODES) | {"sequenceFlow", "laneSet", "dataObject", "dataObjectReference"}
        for child in p:
            tag = child.tag.split("}")[-1]
            if tag not in known and child.tag.startswith("{" + NS["bpmn"]):
                warnings.append(f"process {p.get('id')}: {tag} {child.get('id')} is not kept (outside this plugin's subset)")
        flows = {f.get("id"): f for f in p.findall("bpmn:sequenceFlow", NS)}
        lanes = []
        for ls in p.findall("bpmn:laneSet", NS):
            for lane in ls.findall("bpmn:lane", NS):
                lanes.append({"id": lane.get("id"), "name": lane.get("name"), "set": ls.get("id"),
                              "nodes": [r.text for r in lane.findall("bpmn:flowNodeRef", NS)], "shape": shape(lane.get("id"))})
        objects = {o.get("id"): o for o in p.findall("bpmn:dataObject", NS)}
        data = [{"id": r.get("id"), "name": r.get("name") or (objects.get(r.get("dataObjectRef")) or {}).get("name"),
                 "object": r.get("dataObjectRef"), "shape": shape(r.get("id"))} for r in p.findall("bpmn:dataObjectReference", NS)]
        nodes = []
        for el in p:
            kind = el.tag.split("}")[-1]
            if kind not in FLOW_NODES:
                continue
            extra = {}
            defs = [c.tag.split("}")[-1] for c in el if c.tag.split("}")[-1] in EVENT_DEFS]
            if defs:
                extra["event_definitions"] = defs
            if el.get("default"):
                extra["default"] = el.get("default")
            props = [c.get("id") for c in el.findall("bpmn:property", NS)]
            if props:
                extra["properties"] = props
            outgoing = []
            for fid in [o.text for o in el.findall("bpmn:outgoing", NS)] or [f for f, x in flows.items() if x.get("sourceRef") == el.get("id")]:
                f = flows[fid]
                cond = f.find("bpmn:conditionExpression", NS)
                outgoing.append({k: v for k, v in {"id": fid, "target": f.get("targetRef"), "name": f.get("name"),
                                                   "condition": cond.text if cond is not None else None,
                                                   "di": edges[fid].get("id") if fid in edges else None,
                                                   "waypoints": waypoints(edges.get(fid))}.items() if v not in (None, [])})
            assoc = []
            for tag, direction, ref_tag in (("dataInputAssociation", "in", "sourceRef"), ("dataOutputAssociation", "out", "targetRef")):
                for a in el.findall(f"bpmn:{tag}", NS):
                    r = a.find(f"bpmn:{ref_tag}", NS)
                    t = a.find("bpmn:targetRef", NS)
                    assoc.append({k: v for k, v in {"id": a.get("id"), "direction": direction, "ref": r.text if r is not None else None,
                                                    "property": t.text if direction == "in" and t is not None else None,
                                                    "di": edges[a.get("id")].get("id") if a.get("id") in edges else None,
                                                    "waypoints": waypoints(edges.get(a.get("id")))}.items() if v not in (None, [])})
            nodes.append({"id": el.get("id"), "kind": kind, "name": el.get("name"), "shape": shape(el.get("id")),
                          "outgoing": outgoing, "data": assoc, "bpmn": extra})
        part = participants.get(p.get("id"))
        info = {"definitions": root.get("id"), "target_namespace": root.get("targetNamespace"), "process": p.get("id"),
                "executable": p.get("isExecutable") == "true",
                "lanes": [{k: v for k, v in lane.items() if k != "nodes"} for lane in lanes], "data": data,
                "diagram": diagram.get("id") if diagram is not None else None, "plane": plane.get("id") if plane is not None else None}
        if part is not None:
            info["participant"] = {"id": part.get("id"), "name": part.get("name"), "collaboration": collab.get("id"),
                                   "shape": shape(part.get("id"))}
        out.append({"id": p.get("id"), "name": p.get("name") or (part.get("name") if part is not None else None),
                    "local": slugify(p.get("name") or p.get("id")), "nodes": nodes, "lanes": lanes, "data": data, "bpmn": info})
    return {"processes": out, "warnings": warnings}


# ---- BPMN 2.0 XML out

def layout(acts: list[dict]) -> None:
    """Shapes for activities that have none: columns by distance from the start, rows in order within a column."""
    by = {a["slug"]: a for a in acts}
    incoming = {a["slug"]: 0 for a in acts}
    for a in acts:
        for f in a.get("outgoing") or []:
            if f["to"] in incoming:
                incoming[f["to"]] += 1
    depth, queue = {}, [s for s, n in incoming.items() if n == 0] or [acts[0]["slug"]]
    for s in queue:
        depth.setdefault(s, 0)
    while queue:
        s = queue.pop(0)
        for f in by[s].get("outgoing") or []:
            if f["to"] in by and f["to"] not in depth:
                depth[f["to"]] = depth[s] + 1
                queue.append(f["to"])
    rows: dict[int, int] = {}
    for a in acts:
        d = depth.get(a["slug"], max(depth.values(), default=0) + 1)
        r = rows[d] = rows.get(d, -1) + 1
        w, h = size_of(a["kind"] or "task")
        a["shape"] = {"x": 160 + d * 170 + (100 - w) / 2, "y": 100 + r * 130 + (80 - h) / 2, "width": w, "height": h}


def centre(s: dict, side: str) -> list:
    return [s["x"] + s["width"], s["y"] + s["height"] / 2] if side == "right" else [s["x"], s["y"] + s["height"] / 2]


def export_bpmn(conn, process_slug: str) -> str:
    """A process in Workbench as BPMN 2.0 XML with its diagram, so a BPMN tool opens it as it was drawn (or, for a
    process mapped without a diagram, laid out left to right)."""
    proc = conn.execute("select to_jsonb(x) from api.process x where slug = %s and wb.live(x.id)", (process_slug,)).fetchone()
    if not proc:
        raise SystemExit(f"no live process {process_slug}")
    proc = proc[0]
    domain, info = proc["domain"], proc.get("bpmn") or {}
    acts = [r[0] for r in conn.execute(
        """select to_jsonb(a) from api.activity a join wb.relation r on r.from_id = a.id and r.predicate = 'partOf' and r.to_id = %s
            where wb.live(a.id) order by a.bpmn_id nulls last, a.slug""", (proc["id"],)).fetchall()]
    if not acts:
        raise SystemExit(f"process {process_slug} has no activities")
    for a in acts:
        a["kind"] = a.get("kind") or "task"
        a["bpmn_id"] = a.get("bpmn_id") or ("Activity_" + slugify(local(a["slug"], domain)).replace("-", "_"))
        a["outgoing"] = a.get("outgoing") or [{"to": local(r[0], domain)} for r in conn.execute(
            """select t.slug from wb.relation r join api.activity t on t.id = r.to_id
                where r.from_id = %s and r.predicate = 'flowsTo' order by t.slug""", (a["id"],)).fetchall()]
        a["slug"] = local(a["slug"], domain)
    if any(not a.get("shape") for a in acts):
        layout(acts)
    ids = {a["slug"]: a["bpmn_id"] for a in acts}
    shapes = {a["bpmn_id"]: a["shape"] for a in acts}
    for k, v in NS.items():
        if k != "xsi":
            ET.register_namespace(k, v)
    ET.register_namespace("xsi", NS["xsi"])
    pid = info.get("process") or "Process_" + slugify(local(process_slug, domain)).replace("-", "_")
    root = ET.Element(q("definitions"), {"id": info.get("definitions") or "Definitions_" + pid,
                                         "targetNamespace": info.get("target_namespace") or "http://bpmn.io/schema/bpmn",
                                         "exporter": "workbench business plugin", "exporterVersion": "0.1.0"})
    part = info.get("participant")
    if part:
        c = ET.SubElement(root, q("collaboration"), {"id": part["collaboration"]})
        ET.SubElement(c, q("participant"), {k: v for k, v in {"id": part["id"], "name": part.get("name"), "processRef": pid}.items() if v})
    p = ET.SubElement(root, q("process"), {"id": pid, "name": proc["title"], "isExecutable": "true" if info.get("executable") else "false"})
    lanes = info.get("lanes") or []
    if lanes:
        sets = {}
        performers = {}
        for r in conn.execute("""select a.slug, ro.slug from wb.relation r join api.activity a on a.id = r.from_id
                                  join api.role ro on ro.id = r.to_id where r.predicate = 'performedBy' and a.id = any(%s::uuid[])""",
                              ([a["id"] for a in acts],)).fetchall():
            performers.setdefault(local(r[1], domain), []).append(local(r[0], domain))
        for lane in lanes:
            ls = sets.get(lane.get("set") or "LaneSet_1")
            if ls is None:
                ls = sets[lane.get("set") or "LaneSet_1"] = ET.SubElement(p, q("laneSet"), {"id": lane.get("set") or "LaneSet_1"})
            le = ET.SubElement(ls, q("lane"), {k: v for k, v in {"id": lane["id"], "name": lane.get("name")}.items() if v})
            for s in sorted(performers.get(lane.get("role"), []), key=lambda s: ids[s]):
                ET.SubElement(le, q("flowNodeRef")).text = ids[s]
    data = info.get("data") or []
    for d in data:
        if d.get("object"):
            ET.SubElement(p, q("dataObject"), {"id": d["object"]})
    flows, assoc_edges = [], []
    for a in acts:
        el = ET.SubElement(p, q(a["kind"]), {k: v for k, v in {"id": a["bpmn_id"], "name": a["title"],
                                                                "default": (a.get("bpmn") or {}).get("default")}.items() if v})
        incoming = [(f, b) for b in acts for f in b["outgoing"] if f["to"] == a["slug"]]
        for f, b in incoming:
            ET.SubElement(el, q("incoming")).text = f.get("id") or f"Flow_{b['bpmn_id']}_{a['bpmn_id']}"
        for f in a["outgoing"]:
            fid = f.get("id") or f"Flow_{a['bpmn_id']}_{ids[f['to']]}"
            ET.SubElement(el, q("outgoing")).text = fid
            flows.append((fid, a, f))
        props = list((a.get("bpmn") or {}).get("properties") or [])
        for x in a.get("data") or []:
            if x["direction"] == "in" and not x.get("property"):
                x["property"] = f"Property_{x['id']}"
                props.append(x["property"])
        for pr in props:
            ET.SubElement(el, q("property"), {"id": pr, "name": "__targetRef_placeholder"})
        for x in a.get("data") or []:
            ae = ET.SubElement(el, q("dataInputAssociation" if x["direction"] == "in" else "dataOutputAssociation"), {"id": x["id"]})
            if x["direction"] == "in":
                ET.SubElement(ae, q("sourceRef")).text = x["ref"]
                ET.SubElement(ae, q("targetRef")).text = x["property"]
            else:
                ET.SubElement(ae, q("targetRef")).text = x["ref"]
            assoc_edges.append((a, x))
        for d in (a.get("bpmn") or {}).get("event_definitions") or []:
            ET.SubElement(el, q(d), {"id": f"{d[0].upper()}{d[1:]}_{a['bpmn_id']}"})
    for d in data:
        ET.SubElement(p, q("dataObjectReference"), {k: v for k, v in {"id": d["id"], "name": d.get("name"),
                                                                      "dataObjectRef": d.get("object")}.items() if v})
    for fid, a, f in flows:
        fe = ET.SubElement(p, q("sequenceFlow"), {k: v for k, v in {"id": fid, "name": f.get("name"), "sourceRef": a["bpmn_id"],
                                                                     "targetRef": ids[f["to"]]}.items() if v})
        if f.get("condition"):
            ce = ET.SubElement(fe, q("conditionExpression"), {f"{{{NS['xsi']}}}type": "bpmn:tFormalExpression"})
            ce.text = f["condition"]
    # the diagram
    dg = ET.SubElement(root, q("BPMNDiagram", "bpmndi"), {"id": info.get("diagram") or "BPMNDiagram_1"})
    pl = ET.SubElement(dg, q("BPMNPlane", "bpmndi"), {"id": info.get("plane") or "BPMNPlane_1",
                                                      "bpmnElement": part["collaboration"] if part else pid})

    def put_shape(el_id, s, horizontal=None):
        attrs = {"id": s.get("di") or f"{el_id}_di", "bpmnElement": el_id}
        h = s.get("horizontal", horizontal)
        if h is not None:
            attrs["isHorizontal"] = "true" if h else "false"
        se = ET.SubElement(pl, q("BPMNShape", "bpmndi"), attrs)
        ET.SubElement(se, q("Bounds", "dc"), {k: fmt(s[k]) for k in ("x", "y", "width", "height")})

    if part and part.get("shape"):
        put_shape(part["id"], part["shape"], True)
    for lane in lanes:
        if lane.get("shape"):
            put_shape(lane["id"], lane["shape"], True)
    for a in acts:
        put_shape(a["bpmn_id"], a["shape"])
    for d in data:
        if d.get("shape"):
            put_shape(d["id"], d["shape"])
    data_shapes = {d["id"]: d.get("shape") for d in data}

    def put_edge(el_id, di, points):
        ee = ET.SubElement(pl, q("BPMNEdge", "bpmndi"), {"id": di or f"{el_id}_di", "bpmnElement": el_id})
        for x, y in points:
            ET.SubElement(ee, q("waypoint", "di"), {"x": fmt(x), "y": fmt(y)})

    for fid, a, f in flows:
        put_edge(fid, f.get("di"), f.get("waypoints") or [centre(a["shape"], "right"), centre(shapes[ids[f["to"]]], "left")])
    for a, x in assoc_edges:
        ds = data_shapes.get(x["ref"])
        pts = x.get("waypoints") or ([centre(ds, "right"), centre(a["shape"], "left")] if ds and x["direction"] == "in"
                                     else [centre(a["shape"], "right"), centre(ds, "left")] if ds else None)
        if pts:
            put_edge(x["id"], x.get("di"), pts)
    ET.indent(root, "  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def fmt(v) -> str:
    return str(int(v)) if float(v).is_integer() else str(v)


# ---- the map file out

def export_map(conn, domain: str) -> str:
    """A domain's items and their relations in the map file's format (business:map reads it back)."""
    items, ids = {}, {}
    for type_id in TYPES:
        for it in live_items(conn, type_id, domain):
            ids[it["id"]] = local(it["slug"], domain)
    for type_id in TYPES:
        fields = fields_of(conn, type_id)
        rows = live_items(conn, type_id, domain)
        if not rows:
            continue
        rels: dict[str, dict[str, list]] = {}
        for f, pred, _t, to in relations_from(conn, [r["id"] for r in rows]):
            if pred in PREDICATES and to in ids:
                rels.setdefault(f, {}).setdefault(pred, []).append(ids[to])
        out = {}
        for it in rows:
            name = ids[it["id"]]
            body = {"title": it["title"]} if it["title"] != name else {}
            body.update({k: it[k] for k in fields if it.get(k) not in (None, "", [], {})})
            for pred, targets in sorted(rels.get(it["id"], {}).items()):
                targets = sorted(set(targets))
                body[pred] = targets[0] if len(targets) == 1 else targets
            out[name] = body
        items[type_id] = out
    head = f"# The business map of {domain}, exported from Workbench by the business plugin (business:map reads it back).\n"
    return head + yaml.safe_dump({"domain": domain, "items": items}, sort_keys=False, allow_unicode=True, width=110)


def main(argv: list[str]) -> int:
    sys.path.insert(0, str(HERE.parents[1] / "workbench"))
    from workbench import cli
    if len(argv) != 2 or argv[0] not in ("export-map", "export-bpmn"):
        print("usage: business_plugin.py export-map DOMAIN | export-bpmn PROCESS-SLUG", file=sys.stderr)
        return 2
    with cli.connect() as conn:
        sys.stdout.write(export_map(conn, argv[1]) if argv[0] == "export-map" else export_bpmn(conn, argv[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
