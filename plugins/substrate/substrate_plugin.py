"""Substrate's extractors for Workbench (workbench/workbench/extract.py has the contract).

    substrate:catalog      catalog-info.yaml -> component items (every entity, its kind in `kind`), each value citing
                           its line, and the relations between them (partOf, dependsOn, providesApi, consumesApi)
    substrate:claude-code  .claude/skills/*/SKILL.md -> skill items; .claude/settings.json hooks -> hook items
    substrate:drift        what the map declares (AiResource entries of type skill or hook) against what the
                           repository has: each difference is a gap in the review lane, withdrawn once it closes
    substrate:morphogen    Morphogen's evidence log (<git common dir>/morphogen/evidence.db) -> verdict items, after
                           checking the whole hash chain independently of Morphogen; a broken chain records nothing

They read the repository at WB_SUBSTRATE_ROOT (default: the checkout this plugin is in). Self is not a special
case (S-49): nothing here knows it is reading Substrate; any repository with these files reads the same way.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
import tempfile
import urllib.error
import urllib.parse
import urllib.request
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


def fetch_json(url: str):
    """(raw bytes, parsed) from a registry's JSON API, or None if it does not answer."""
    req = urllib.request.Request(url, headers={"User-Agent": "substrate-workbench", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
        return raw, json.loads(raw)
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None


def quoted(key, value, pointer):
    return {"quote": f"{json.dumps(key)}: {json.dumps(value)}", "span": {"pointer": pointer}}


def registry_facts(c: dict) -> list[tuple[str, bytes, dict, dict]]:
    """A candidate's licence, releases and activity, as its registries state them: one (url, raw answer, values,
    evidence) per answer, each value quoting the key it was read from. Missing answers are left out."""
    out = []
    repo = c.get("repository")
    if repo:
        url = f"https://api.github.com/repos/{repo}"
        got = fetch_json(url)
        if got:
            raw, d = got
            lic = (d.get("license") or {}).get("spdx_id")
            values = {"licence": lic, "last_push": (d.get("pushed_at") or "")[:10] or None,
                      "stars": d.get("stargazers_count"), "archived": d.get("archived")}
            quotes = {"licence": quoted("spdx_id", lic, "/license/spdx_id"),
                      "last_push": quoted("pushed_at", d.get("pushed_at"), "/pushed_at"),
                      "stars": quoted("stargazers_count", d.get("stargazers_count"), "/stargazers_count"),
                      "archived": quoted("archived", d.get("archived"), "/archived")}
            out.append((url, raw, {k: v for k, v in values.items() if v is not None}, quotes))
        if not c.get("package"):
            url = f"https://api.github.com/repos/{repo}/releases?per_page=20"
            got = fetch_json(url)
            if got:
                raw, rels = got
                for n, r in enumerate(rels if isinstance(rels, list) else []):
                    if not r.get("prerelease") and not r.get("draft"):
                        out.append((url, raw, {"latest_release": r.get("tag_name"), "released_on": (r.get("published_at") or "")[:10]},
                                    {"latest_release": quoted("tag_name", r.get("tag_name"), f"/{n}/tag_name"),
                                     "released_on": quoted("published_at", r.get("published_at"), f"/{n}/published_at")}))
                        break
    pkg = c.get("package")
    if pkg:
        url = f"https://api.deps.dev/v3/systems/{pkg['system']}/packages/{urllib.parse.quote(pkg['name'], safe='')}"
        got = fetch_json(url)
        if got:
            raw, d = got
            versions = [(n, v) for n, v in enumerate(d.get("versions") or []) if v.get("publishedAt")]
            if versions:
                n, v = max(versions, key=lambda nv: nv[1]["publishedAt"])
                ver = v["versionKey"]["version"]
                out.append((url, raw, {"latest_release": ver, "released_on": v["publishedAt"][:10]},
                            {"latest_release": quoted("version", ver, f"/versions/{n}/versionKey/version"),
                             "released_on": quoted("publishedAt", v["publishedAt"], f"/versions/{n}/publishedAt")}))
                vurl = f"{url}/versions/{urllib.parse.quote(ver, safe='')}"
                got = fetch_json(vurl)
                if got and got[1].get("licenses"):
                    lic = " AND ".join(got[1]["licenses"])
                    out.append((vurl, got[0], {"licence": lic}, {"licence": quoted("licenses", got[1]["licenses"], "/licenses")}))
    return out


GENESIS = "0" * 64


def canonical(obj) -> str:
    """Morphogen's canonical JSON (morphogen/evidence.py), which its hashes cover."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class ChainBroken(Exception):
    pass


def read_evidence(path: Path) -> list[dict]:
    """Every record, oldest first, after checking the chain: each record's hash covers its canonical JSON without
    the hash, and names the one before it. Read from a copy, so a writer's WAL and a read-only mount do not clash."""
    with tempfile.TemporaryDirectory() as d:
        for suffix in ("", "-wal", "-shm"):
            if Path(str(path) + suffix).exists():
                shutil.copy(str(path) + suffix, Path(d) / ("evidence.db" + suffix))
        c = sqlite3.connect(Path(d) / "evidence.db")
        try:
            rows = c.execute("SELECT seq, raw FROM evidence ORDER BY seq").fetchall()
        finally:
            c.close()
    out, prev = [], GENESIS
    for i, (seq, raw) in enumerate(rows, start=1):
        rec = json.loads(raw)
        body = {k: v for k, v in rec.items() if k != "hash"}
        if seq != i or rec.get("seq") != i or rec.get("prev") != prev or \
                hashlib.sha256(canonical(body).encode()).hexdigest() != rec.get("hash"):
            raise ChainBroken(f"the evidence log is broken at record {i}: its hash or its link does not match")
        prev = rec["hash"]
        out.append(rec)
    return out


def git_common_dir(root: Path) -> Path:
    g = root / ".git"
    if g.is_file():                                      # a worktree: .git names the real git dir
        real = Path(g.read_text().split(":", 1)[1].strip())
        common = real / "commondir"
        return (real / common.read_text().strip()).resolve() if common.is_file() else real
    return g


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

    def morphogen(ctx, inputs):
        path = Path(inputs.get("log") or wb.setting("evidence") or git_common_dir(root) / "morphogen" / "evidence.db")
        if not path.is_file():
            ctx.log(f"no evidence log at {path}: Morphogen has not judged anything here yet")
            return
        records = read_evidence(path)                     # raises on a broken chain: the run fails, nothing is kept
        components = dict(ctx.conn.execute("select slug, id from api.component").fetchall())
        verdicts = [r for r in records if r.get("kind") == "verdict" and r.get("by") == "judge"]
        for rec in verdicts:
            data = canonical(rec).encode()
            src = ctx.source(f"morphogen:evidence.db#{rec['seq']}", data, "application/json")
            part = rec.get("cell") or (rec.get("subject") or {}).get("system") or ""
            outcome = rec.get("outcome") or {}
            fields = {"claim": rec.get("claim"), "verdict": rec.get("verdict"), "gate": (rec.get("gate") or {}).get("decision"),
                      "cell": part, "base": (rec.get("refs") or {}).get("base"), "candidate": (rec.get("refs") or {}).get("candidate"),
                      "trust": rec.get("trust"), "metrics": outcome.get("metrics") or {},
                      "reasons": {k: outcome.get(k) for k in ("forbidden", "denied", "check", "interfaces", "wrong", "failed") if k in outcome},
                      "seq": rec["seq"], "hash": rec["hash"]}
            ev = {f: {"quote": f"{rec['claim']}" if f == "claim" else json.dumps(rec.get(k), sort_keys=True)[:300],
                      "span": {"record": rec["seq"], "pointer": "/" + k}}
                  for f, k in (("claim", "claim"), ("verdict", "verdict"), ("gate", "gate"), ("trust", "trust"))}
            item = ctx.upsert("verdict", f"{re.sub(r'[^a-z0-9]+', '-', part.lower()).strip('-') or 'system'}-{rec['seq']}",
                              {k: v for k, v in fields.items() if v is not None},
                              title=rec.get("claim") or f"verdict {rec['seq']}", source=src, evidence=ev)
            target = components.get(part.split("/")[-1])
            if target:
                ctx.relate("verdict", item, "judges", "component", target)
        ctx.done("verdict")
        ctx.log(f"{len(records)} records in a sound chain, {len(verdicts)} verdicts")

    def choices(ctx, inputs):
        folder = root / inputs.get("folder", "docs/choices")
        counts = {"choices": 0, "candidates": 0, "registry": 0, "unreached": 0}
        for path in sorted(folder.glob("*.yaml")):
            rel = str(path.relative_to(root))
            data = path.read_bytes()
            text = data.decode()
            lines = text.splitlines()
            node = yaml.compose(text)
            doc = yaml.safe_load(text) or {}
            spans = line_spans(node)
            src = ctx.source(f"file:{rel}", data, "application/yaml")
            fields = {k: doc.get(k) for k in ("question", "asked_by", "need", "searched", "trial", "verdict", "pick", "reason")}
            ev = {k: e for k in fields if (e := evidence(lines, spans, (k,)))}
            if (e := evidence(lines, spans, ("question",))):
                ev["title"] = e
            choice = ctx.upsert("choice", path.stem, {k: v for k, v in fields.items() if v is not None},
                                title=doc.get("question") or path.stem, source=src, evidence=ev)
            counts["choices"] += 1
            for i, c in enumerate(doc.get("candidates") or []):
                name = c["name"]
                facts = registry_facts(c)
                item = None
                for url, raw, values, quotes in facts:
                    rsrc = ctx.source(url, raw, "application/json")
                    item = ctx.upsert("candidate", name, values, title=c.get("title") or name, source=rsrc, evidence=quotes)
                    counts["registry"] += 1
                if not facts:
                    counts["unreached"] += 1
                own = {k: c.get(k) for k in ("registry", "repository", "image", "fit", "trial", "shortlisted", "outcome", "reason")}
                cev = {k: e for k in own if (e := evidence(lines, spans, ("candidates", i, k)))}
                item = ctx.upsert("candidate", name, {k: v for k, v in own.items() if v is not None},
                                  title=c.get("title") or name, source=src, evidence=cev)
                ctx.relate("choice", choice, "considered", "candidate", item)
                if c.get("outcome") == "picked" or name == doc.get("pick"):
                    ctx.relate("choice", choice, "picks", "candidate", item)
                counts["candidates"] += 1
        ctx.done("choice")
        ctx.done("candidate")
        ctx.log(f"{counts['choices']} choices, {counts['candidates']} candidates, {counts['registry']} registry answers"
                + (f"; {counts['unreached']} candidates' registries did not answer (their earlier claims stand)" if counts["unreached"] else ""))

    wb.extractor("choices", choices, "docs/choices/*.yaml: each choice and its candidates, licence and releases quoted from the registry")
    wb.extractor("catalog", catalog, "catalog-info.yaml: every entity as a component item, citing its line, with its relations")
    wb.extractor("claude-code", claude_code, "Claude Code's .claude/: skills and hooks as items")
    wb.extractor("morphogen", morphogen, "Morphogen's evidence log: each verdict, after checking the whole hash chain")
    wb.extractor("drift", drift, "what the map declares against what the repository has; each difference to the review lane")
