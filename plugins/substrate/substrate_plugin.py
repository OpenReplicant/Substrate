"""Substrate's extractors for Workbench (workbench/workbench/extract.py has the contract).

    substrate:catalog      catalog-info.yaml -> component items (every entity, its kind in `kind`), each value citing
                           its line, and the relations between them (partOf, dependsOn, providesApi, consumesApi)
    substrate:claude-code  .claude/skills/*/SKILL.md -> skill items; .claude/settings.json hooks -> hook items
    substrate:drift        what the map declares (AiResource entries of type skill or hook) against what the
                           repository has: each difference is a gap in the review lane, withdrawn once it closes

They read the repository at WB_SUBSTRATE_ROOT (default: the checkout this plugin is in). Self is not a special
case (S-49): nothing here knows it is reading Substrate; any repository with these files reads the same way.
"""
from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath

import yaml

NODE_KINDS = {"component", "resource", "airesource"}
RELATIONS = {"system": "partOf", "domain": "partOf", "subcomponentOf": "partOf", "dependsOn": "dependsOn",
             "providesApis": "providesApi", "consumesApis": "consumesApi", "owner": "ownedBy"}
DEFAULT_KIND = {"system": "system", "domain": "domain", "subcomponentOf": "component", "providesApis": "api",
                "consumesApis": "api", "owner": "group"}


def slug_for(kind: str, name: str) -> str:
    """Components, resources and AI resources keep their name (so a skill's entry and the skill meet); other
    kinds are prefixed, since a system and a component may share a name."""
    return name if kind.lower() in NODE_KINDS else f"{kind.lower()}-{name}"


def parse_ref(ref: str, field: str) -> tuple[str | None, str]:
    kind, _, rest = str(ref).rpartition(":")
    kind = kind or DEFAULT_KIND.get(field)
    return (kind.lower() if kind else None), rest.split("/")[-1]


def line_spans(node, path=()):
    """{path: (first line, last line)} for a composed YAML node, 1-based."""
    out = {path: (node.start_mark.line + 1, max(node.start_mark.line + 1, node.end_mark.line + (1 if node.end_mark.column else 0)))}
    if isinstance(node, yaml.MappingNode):
        for k, v in node.value:
            out.update(line_spans(v, path + (k.value,)))
            out[path + (k.value,)] = (k.start_mark.line + 1, out[path + (k.value,)][1])
    elif isinstance(node, yaml.SequenceNode):
        for i, v in enumerate(node.value):
            out.update(line_spans(v, path + (i,)))
    return out


def evidence(lines, spans, path):
    a, b = spans.get(path, (None, None))
    if not a:
        return None
    return {"quote": "\n".join(lines[a - 1:min(b, a + 2)]).strip(), "span": {"start_line": a, "end_line": b}}


def register(wb):
    root = Path(wb.setting("root") or wb.folder.parents[1])

    def catalog(ctx, inputs):
        rel = inputs.get("file", "catalog-info.yaml")
        path = root / rel
        data = path.read_bytes()
        text = data.decode()
        lines = text.splitlines()
        src = ctx.source(f"file:{rel}", data, "application/yaml")
        entries = []
        for node in yaml.compose_all(text):
            if node is None:
                continue
            doc = yaml.safe_load(yaml.serialize(node))
            spans = line_spans(node)
            kind, md, spec = str(doc.get("kind", "")), doc.get("metadata") or {}, doc.get("spec") or {}
            if not md.get("name") or kind.lower() == "location":
                continue
            fields = {"kind": kind, "type": spec.get("type"), "lifecycle": spec.get("lifecycle"),
                      "description": md.get("description"), "owner": spec.get("owner"), "system": spec.get("system"),
                      "annotations": md.get("annotations")}
            where = {"kind": ("kind",), "type": ("spec", "type"), "lifecycle": ("spec", "lifecycle"),
                     "description": ("metadata", "description"), "owner": ("spec", "owner"), "system": ("spec", "system"),
                     "annotations": ("metadata", "annotations"), "title": ("metadata", "name")}
            ev = {f: e for f, p in where.items() if (e := evidence(lines, spans, p))}
            item = ctx.upsert("component", slug_for(kind, md["name"]), {k: v for k, v in fields.items() if v is not None},
                              title=md.get("title") or md["name"], source=src, evidence=ev)
            entries.append((kind.lower(), md["name"], item, spec))
        ids = {(k, n): i for k, n, i, _ in entries}
        missing = set()
        for kind, name, item, spec in entries:
            for field, predicate in RELATIONS.items():
                refs = spec.get(field)
                for ref in (refs if isinstance(refs, list) else [refs] if refs else []):
                    k, n = parse_ref(ref, field)
                    target = ids.get((k or "component", n))
                    if target:
                        ctx.relate("component", item, predicate, "component", target)
                    else:
                        missing.add(f"{field}: {ref}")
        ctx.done("component")
        if missing:
            ctx.log(f"{len(missing)} refs to entities this file does not define: {', '.join(sorted(missing)[:8])}")

    def claude_code(ctx, inputs):
        found_skills, found_hooks = 0, 0
        for f in sorted((root / ".claude/skills").glob("*/SKILL.md")):
            rel = str(f.relative_to(root))
            data = f.read_bytes()
            lines = data.decode().splitlines()
            front, at = {}, {}
            if lines and lines[0].strip() == "---":
                for n, line in enumerate(lines[1:], 2):
                    if line.strip() == "---":
                        break
                    m = re.match(r"^([A-Za-z][\w-]*):\s*(.*)$", line)
                    if m:
                        front[m.group(1)], at[m.group(1)] = m.group(2).strip().strip("\"'"), n
            name = front.get("name") or f.parent.name
            src = ctx.source(f"file:{rel}", data, "text/markdown")
            ev = {k: {"quote": lines[at[k] - 1], "span": {"start_line": at[k], "end_line": at[k]}} for k in ("description",) if k in at}
            if "name" in at:
                ev["title"] = {"quote": lines[at["name"] - 1], "span": {"start_line": at["name"], "end_line": at["name"]}}
            ctx.upsert("skill", name, {"description": front.get("description"), "path": rel, "agents": ["claude-code"]},
                       title=name, source=src, evidence=ev)
            found_skills += 1
        settings = root / ".claude/settings.json"
        if settings.is_file():
            data = settings.read_bytes()
            text = data.decode()
            lines = text.splitlines()
            src = ctx.source("file:.claude/settings.json", data, "application/json")
            for event, groups in (json.loads(text).get("hooks") or {}).items():
                for n, group in enumerate(g for grp in [groups or []] for g in grp):
                    for i, h in enumerate(group.get("hooks") or []):
                        command = h.get("command") or h.get("prompt") or ""
                        script = next((PurePosixPath(w).name.rsplit(".", 1)[0] for w in re.split(r"\s+", command.replace('"', " "))
                                       if "/" in w or re.search(r"\.(py|sh|js|ts|mjs)$", w)), None)
                        slug = re.sub(r"[^a-z0-9]+", "-", f"{event}-{script or n + 1}".lower()).strip("-")
                        at = next((k for k, line in enumerate(lines, 1) if command and command[:40].replace('"', '\\"')[:30] in line), None)
                        ev = {"command": {"quote": lines[at - 1].strip(), "span": {"start_line": at, "end_line": at}}} if at else {}
                        ctx.upsert("hook", slug, {"event": event, "matcher": group.get("matcher"), "command": command,
                                                  "path": ".claude/settings.json"}, title=slug, source=src, evidence=ev)
                        found_hooks += 1
        ctx.done("skill")
        ctx.done("hook")
        ctx.log(f"{found_skills} skills, {found_hooks} hooks")

    def drift(ctx, inputs):
        q = ctx.conn.execute
        declared = {}
        for slug, typ, title in q("""select c.slug, c.type, c.title from api.component c
                                     where c.kind = 'AiResource' and c.type in ('skill', 'hook') and exists (
                                       select 1 from wb.claim cl where cl.subject_id = c.id and cl.status = 'current'
                                         and cl.author = 'substrate:catalog')""").fetchall():
            declared[(typ, slug)] = title
        observed = {}
        for typ in ("skill", "hook"):
            for slug, path in q(f"""select i.slug, i.path from api.{typ} i where exists (
                                     select 1 from wb.claim cl where cl.subject_id = i.id and cl.status = 'current'
                                       and cl.author = 'substrate:claude-code')""").fetchall():
                observed[(typ, slug)] = path
        if not declared and not observed:
            ctx.log("nothing declared or observed yet: run substrate:catalog and substrate:claude-code first")
            return
        for (typ, slug), path in sorted(observed.items()):
            if (typ, slug) not in declared:
                ctx.decision("gap", f"undeclared:{typ}:{slug}", {
                    "text": f"The repository has the {typ} {slug}, which the map does not declare.",
                    "observed": {"type": typ, "slug": slug, "path": path}, "direction": "declare it, or remove it"})
        for (typ, slug), title in sorted(declared.items()):
            if (typ, slug) not in observed:
                ctx.decision("gap", f"unobserved:{typ}:{slug}", {
                    "text": f"The map declares the {typ} {slug}; the repository has none by that name.",
                    "declared": {"type": typ, "slug": slug}, "direction": "build it, or take it off the map"})
        ctx.log(f"{len(declared)} declared, {len(observed)} observed")

    wb.extractor("catalog", catalog, "catalog-info.yaml: every entity as a component item, citing its line, with its relations")
    wb.extractor("claude-code", claude_code, "Claude Code's .claude/: skills and hooks as items")
    wb.extractor("drift", drift, "what the map declares against what the repository has; each difference to the review lane")
