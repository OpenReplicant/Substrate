"""Substrate's extractors for Workbench (workbench/workbench/extract.py has the contract).

    substrate:catalog      catalog-info.yaml -> component items (every entity, its kind in `kind`), each value citing
                           its line, and the relations between them (partOf, dependsOn, providesApi, consumesApi)
    substrate:claude-code  .claude/skills/*/SKILL.md -> skill items; .claude/settings.json hooks -> hook items
    substrate:drift        what the map declares (AiResource entries of type skill or hook) against what the
                           repository has: each difference is a gap in the review lane, withdrawn once it closes
    substrate:observed     the snapshots plugins/substrate/observe.py wrote in .state/observed/<host>/ -> host,
                           container, image, volume, setting, route, api, plugin, ui, connection and cell items, each
                           value quoting its snapshot by JSON pointer, and how they relate (OBSERVE.md)
    substrate:morphogen    Morphogen's evidence log (<git common dir>/morphogen/evidence.db) -> verdict items, after
                           checking the whole hash chain independently of Morphogen; a broken chain records nothing

They read the repository at WB_SUBSTRATE_ROOT (default: the checkout this plugin is in). Self is not a special
case (S-49): nothing here knows it is reading Substrate; any repository with these files reads the same way.
"""
from __future__ import annotations

import fnmatch
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


OBSERVED_KINDS = ("container", "volume", "route", "api", "plugin", "ui", "connection")   # what drift asks the map to account for


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9.]+", "-", str(text).lower()).strip("-.") or "x"


def route_slug(match: list) -> str:
    """A route's name from what it matches: /api/* is api-any, a named regexp is re-<name>, no matcher is all."""
    parts = []
    for m in match or []:
        for p in m.get("path") or []:
            parts.append(slugify(p.replace("*", "any")) if p.strip("/") else "root")
        rx = m.get("path_regexp")
        if isinstance(rx, dict) and rx.get("pattern"):
            parts.append(f"re-{slugify(rx.get('name') or rx['pattern'])}")
        for h in m.get("host") or []:
            parts.append(f"host-{slugify(h)}")
    return "-".join(parts) or "all"


def walk_handlers(handlers: list) -> tuple[list, list]:
    """(handler names in order, upstream dials) through any subroutes."""
    names, dials = [], []
    for h in handlers or []:
        names.append(h.get("handler"))
        dials += [u.get("dial") for u in h.get("upstreams") or [] if u.get("dial")]
        for r in h.get("routes") or []:
            n, d = walk_handlers(r.get("handle"))
            names += n
            dials += d
    return names, dials


def matches(route_match: list, path: str) -> bool:
    if not route_match:
        return True
    for m in route_match:
        if any(fnmatch.fnmatchcase(path, p) for p in m.get("path") or []):
            return True
        rx = m.get("path_regexp")
        if isinstance(rx, dict) and rx.get("pattern") and re.search(rx["pattern"], path):
            return True
    return False


def snapd(snap: dict) -> dict:
    """A snapshot's data when it is an object (an HTTP, probe or command snapshot), else {}."""
    d = snap.get("data")
    return d if isinstance(d, dict) else {}


def at(pointer: str, value) -> dict:
    return {"quote": json.dumps(value, sort_keys=True, default=str)[:300], "span": {"pointer": pointer}}


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
        """The map against what is there. Skills and hooks meet their map entries by name (step 2). Every other
        observed kind meets the declared part whose substrate.dev/observed-as names it: a comma-separated list of
        <type>:<slug>, where a slug may be a glob (route:front-*). Each difference is a gap for review."""
        q = ctx.conn.execute
        current = lambda author: f"""exists (select 1 from wb.claim cl where cl.subject_id = i.id and cl.status = 'current'
                                       and cl.author = '{author}')"""  # noqa: E731
        declared = {}
        for slug, typ, title in q(f"""select i.slug, i.type, i.title from api.component i
                                      where i.kind = 'AiResource' and i.type in ('skill', 'hook') and {current('substrate:catalog')}""").fetchall():
            declared[(typ, slug)] = title
        observed = {}
        for typ in ("skill", "hook"):
            for slug, path in q(f"select i.slug, i.path from api.{typ} i where {current('substrate:claude-code')}").fetchall():
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

        # every other kind: what runs and is served, against observed-as
        running = {}
        for typ in OBSERVED_KINDS:
            for iid, slug, title in q(f"select i.id, i.slug, i.title from api.{typ} i where {current('substrate:observed')}").fetchall():
                running[(typ, slug)] = (str(iid), title)
        claimed, refs = {}, 0
        for cid, slug, kind, ann in q(f"""select i.id, i.slug, i.kind, i.annotations from api.component i
                                          where i.annotations ? 'substrate.dev/observed-as' and {current('substrate:catalog')}""").fetchall():
            for ref in str(ann["substrate.dev/observed-as"]).split(","):
                typ, _, pattern = ref.strip().partition(":")
                if typ not in OBSERVED_KINDS or not pattern:
                    ctx.log(f"{slug}: observed-as {ref.strip()!r} is not <type>:<slug> for a type drift reads ({', '.join(OBSERVED_KINDS)})")
                    continue
                refs += 1
                hits = [k for k in running if k[0] == typ and fnmatch.fnmatchcase(k[1], pattern)]
                for k in hits:
                    claimed.setdefault(k, []).append(slug)
                    ctx.relate("component", str(cid), "observedAs", typ, running[k][0])
                if not hits:
                    ctx.decision("gap", f"unobserved:{typ}:{pattern}", {
                        "text": f"The map says {kind} {slug} runs as the {typ} {pattern}; nothing by that name was observed.",
                        "declared": {"type": "component", "slug": slug, "observed_as": ref.strip()},
                        "direction": "start or build it, or change the map"})
        for (typ, slug), (iid, title) in sorted(running.items()):
            if (typ, slug) not in claimed:
                ctx.decision("gap", f"undeclared:{typ}:{slug}", {
                    "text": f"The {typ} {title} was observed here, and no part on the map says it is theirs.",
                    "observed": {"type": typ, "slug": slug, "id": iid, "title": title},
                    "direction": "declare it (observed-as on a part, or a new entry), or remove it"})
        ctx.log(f"{len(declared)} skills and hooks declared, {len(observed)} found; {refs} observed-as refs, "
                f"{len(running)} running or served, {len(claimed)} accounted for")

    def observed(ctx, inputs):
        """The snapshots observe.py wrote, every host folder in .state/observed/, into items (OBSERVE.md)."""
        base = root / inputs.get("folder", ".state/observed")
        hosts = sorted(p for p in base.glob("*/index.json")) if base.is_dir() else []
        if not hosts:
            ctx.log(f"no snapshots in {base.relative_to(root) if base.is_relative_to(root) else base}: run scripts/observe.sh first")
            return
        counts: dict[str, int] = {}
        components = dict(ctx.conn.execute("select slug, id from api.component").fetchall())

        def put(typ, slug, fields, title, src, ev):
            counts[typ] = counts.get(typ, 0) + 1
            return ctx.upsert(typ, slug, {k: v for k, v in fields.items() if v is not None}, title=title, source=src,
                              evidence={k: v for k, v in ev.items() if k in fields and fields[k] is not None or k == "title"})

        for index in hosts:
            folder = index.parent
            snaps, sources = {}, {}
            for f in sorted(folder.glob("*.json")):
                if f.name == "index.json":
                    continue
                raw = f.read_bytes()
                snaps[f.stem] = json.loads(raw)
                sources[f.stem] = ctx.source(f"file:{f.relative_to(root)}", raw, "application/json")
            h = snaps.get("host", {}).get("data") or {}
            src = sources.get("host")
            host = put("host", slugify(h.get("hostname") or folder.name), {
                "os": (h.get("os") or {}).get("PRETTY_NAME"), "kernel": h.get("kernel"), "arch": h.get("arch"),
                "cpus": h.get("cpus"), "cpu_model": h.get("cpu_model"), "memory_bytes": h.get("memory_bytes"),
                "engine": (h.get("engine") or {}).get("name"), "engine_version": (h.get("engine") or {}).get("version")},
                h.get("hostname") or folder.name, src, {
                "title": at("/data/hostname", h.get("hostname")), "os": at("/data/os/PRETTY_NAME", (h.get("os") or {}).get("PRETTY_NAME")),
                "kernel": at("/data/kernel", h.get("kernel")), "arch": at("/data/arch", h.get("arch")), "cpus": at("/data/cpus", h.get("cpus")),
                "cpu_model": at("/data/cpu_model", h.get("cpu_model")), "memory_bytes": at("/data/memory_bytes", h.get("memory_bytes")),
                "engine": at("/data/engine/name", (h.get("engine") or {}).get("name")),
                "engine_version": at("/data/engine/version", (h.get("engine") or {}).get("version"))})

            # images, then containers (which run them and mount volumes), then volumes
            images, image_by_id = snaps.get("images", {}).get("data") or [], {}
            used = {c.get("image") for c in snaps.get("containers", {}).get("data") or []}
            for n, im in enumerate(images):
                tag = next((t for t in im.get("tags") or [] if t in used), (im.get("tags") or [None])[0])
                name = tag.split("/")[-1] if tag else (im.get("id") or "")[:12]
                image_by_id[im.get("id")] = put("image", slugify(name), {
                    "tags": im.get("tags"), "digest": im.get("digest"), "repo_digests": im.get("digests"), "created": im.get("created"),
                    "size": im.get("size"), "labels": im.get("labels") or None}, tag or name, sources["images"], {
                    "title": at(f"/data/{n}/tags", im.get("tags")), "tags": at(f"/data/{n}/tags", im.get("tags")),
                    "digest": at(f"/data/{n}/digest", im.get("digest")), "repo_digests": at(f"/data/{n}/digests", im.get("digests")),
                    "created": at(f"/data/{n}/created", im.get("created")), "size": at(f"/data/{n}/size", im.get("size")),
                    "labels": at(f"/data/{n}/labels", im.get("labels"))})
            containers = snaps.get("containers", {}).get("data") or []
            volumes = snaps.get("volumes", {}).get("data") or []
            used_by: dict[str, list] = {}
            by_alias: dict[tuple, str] = {}
            cids, cslugs = {}, {}
            for n, c in enumerate(containers):
                slug = slugify(f"{c['project']}-{c['service']}" if c.get("project") and c.get("service") else c["name"])
                p = f"/data/{n}"
                fields = {k: c.get(k) for k in ("name", "project", "service", "image", "digest", "state", "health", "started_at",
                                                 "user", "read_only", "restart_policy", "ports", "mounts", "networks", "env_names")}
                ev = {k: at(f"{p}/{k}", c.get(k)) for k in fields}
                ev["title"] = at(f"{p}/name", c.get("name"))
                cid = put("container", slug, fields, c["name"], sources["containers"], ev)
                cids[c["name"]], cslugs[c["name"]] = cid, slug
                ctx.relate("host", host, "runs", "container", cid, source=sources["containers"])
                if c.get("image_id") in image_by_id:
                    ctx.relate("container", cid, "runsImage", "image", image_by_id[c["image_id"]], source=sources["containers"])
                for m in c.get("mounts") or []:
                    if m.get("type") == "volume" and m.get("name"):
                        used_by.setdefault(m["name"], []).append(c["name"])
                for net, info in (c.get("networks") or {}).items():
                    for a in info.get("aliases") or []:
                        by_alias[(net, a)] = c["name"]
                for name in c.get("env_names") or []:
                    sid = put("setting", slugify(f"{slug}.{name}"), {"name": name, "where": "container environment", "of": c["name"]},
                              name, sources["containers"], {"name": at(f"{p}/env_names", c.get("env_names")),
                                                             "title": at(f"{p}/env_names", c.get("env_names"))})
                    ctx.relate("setting", sid, "configures", "container", cid, source=sources["containers"])
            vids = {}
            for n, v in enumerate(volumes):
                vids[v["name"]] = put("volume", slugify(v["name"]), {
                    "driver": v.get("driver"), "mountpoint": v.get("mountpoint"), "created": v.get("created"),
                    "labels": v.get("labels") or None, "used_by": used_by.get(v["name"], [])}, v["name"], sources["volumes"], {
                    "title": at(f"/data/{n}/name", v["name"]), "driver": at(f"/data/{n}/driver", v.get("driver")),
                    "mountpoint": at(f"/data/{n}/mountpoint", v.get("mountpoint")), "created": at(f"/data/{n}/created", v.get("created")),
                    "labels": at(f"/data/{n}/labels", v.get("labels")),
                    "used_by": {"quote": f"mounted by {', '.join(used_by.get(v['name'], [])) or 'no container'}",
                                "span": {"pointer": "/data", "derived_from": "containers.json mounts"}}})
            for n, c in enumerate(containers):
                for m in c.get("mounts") or []:
                    if m.get("type") == "volume" and m.get("name") in vids:
                        ctx.relate("container", cids[c["name"]], "mounts", "volume", vids[m["name"]], source=sources["containers"])

            # setting names in env files and in Claude Code's settings
            for fn, f in enumerate(snaps.get("env-files", {}).get("data") or []):
                for kn, k in enumerate(f.get("keys") or []):
                    put("setting", slugify(f"{f['file']}.{k['name']}"), {"name": k["name"], "where": "env file", "of": f["file"], "line": k["line"]},
                        k["name"], sources["env-files"], {"name": at(f"/data/{fn}/keys/{kn}/name", k["name"]),
                                                           "title": at(f"/data/{fn}/keys/{kn}/name", k["name"]),
                                                           "line": at(f"/data/{fn}/keys/{kn}/line", k["line"])})
            cc = snaps.get("claude-code", {}).get("data") or {}
            for sn, st in enumerate(cc.get("settings") or []):
                for kn, k in enumerate(st.get("keys") or []):
                    put("setting", slugify(f"{st['file']}.{k}"), {"name": k, "where": "Claude Code settings", "of": st["file"]},
                        k, sources["claude-code"], {"name": at(f"/data/settings/{sn}/keys/{kn}", k), "title": at(f"/data/settings/{sn}/keys/{kn}", k)})
                for kn, k in enumerate(st.get("env_names") or []):
                    put("setting", slugify(f"{st['file']}.env.{k}"), {"name": k, "where": "Claude Code settings env", "of": st["file"]},
                        k, sources["claude-code"], {"name": at(f"/data/settings/{sn}/env_names/{kn}", k), "title": at(f"/data/settings/{sn}/env_names/{kn}", k)})

            # routes, from each web server's running configuration
            routes_of: dict[str, list] = {}
            for name, snap in snaps.items():
                d = snapd(snap)
                if not name.startswith("probe-") or d.get("kind") != "caddy" or not d.get("data"):
                    continue
                cname = d["container"]
                container = next((c for c in containers if c["name"] == cname), {})
                nets = list((container.get("networks") or {}))
                for server, sv in (d["data"].get("servers") or {}).items():
                    seen = set()
                    for order, r in enumerate(sv.get("routes") or []):
                        slug = f"{cslugs.get(cname, slugify(cname))}-{slugify(server)}-{route_slug(r.get('match'))}"
                        while slug in seen:
                            slug += "-next"
                        seen.add(slug)
                        handlers, dials = walk_handlers(r.get("handle"))
                        p = f"/data/data/servers/{server}/routes/{order}"
                        rid = put("route", slug, {"server": f"{cname} {server}", "listen": sv.get("listen"), "order": order,
                                                  "match": r.get("match") or [], "handlers": handlers, "upstreams": dials},
                                  " ".join(p for m in r.get("match") or [] for p in (m.get("path") or [m.get("path_regexp", {}).get("pattern", "")]))
                                  or f"{server} (every request)", sources[name], {
                                  "title": at(f"{p}/match", r.get("match")), "server": at(f"/data/data/servers/{server}/listen", sv.get("listen")),
                                  "listen": at(f"/data/data/servers/{server}/listen", sv.get("listen")), "order": at(p, order),
                                  "match": at(f"{p}/match", r.get("match")), "handlers": at(f"{p}/handle", r.get("handle")),
                                  "upstreams": at(f"{p}/handle", dials)})
                        if cname in cids:
                            ctx.relate("container", cids[cname], "serves", "route", rid, source=sources[name])
                        for dial in dials:
                            target = next((by_alias[(n, dial.rsplit(":", 1)[0])] for n in nets if (n, dial.rsplit(":", 1)[0]) in by_alias), None)
                            if target:
                                ctx.relate("route", rid, "proxiesTo", "container", cids[target], source=sources[name])
                        routes_of.setdefault(cname, []).append((r.get("match"), rid, bool(dials) or "file_server" in handlers
                                                                or "static_response" in handlers or "rewrite" in handlers))

            def route_for(url: str):
                """The route that serves a URL on this host: the container publishing its port, its first matching route."""
                u = urllib.parse.urlsplit(url)
                port = str(u.port or (443 if u.scheme == "https" else 80))
                owner = next((c["name"] for c in containers for pt in c.get("ports") or [] if pt.get("host_port") == port), None)
                return next((rid for m, rid, terminal in routes_of.get(owner, []) if m and matches(m, u.path or "/")), None) \
                    or next((rid for m, rid, terminal in reversed(routes_of.get(owner, [])) if not m and terminal), None)

            # what is served over HTTP: APIs, plugins, the shell's modules
            apis_by_url = {}
            for name, snap in snaps.items():
                d = snapd(snap)
                if not name.startswith("http-") or not d.get("data"):
                    continue
                kind, body = d.get("kind"), d["data"]
                if kind in ("openapi", "mcp"):
                    ops = ([f"{m.upper()} {p}" for p, o in (body.get("paths") or {}).items() for m in o] if kind == "openapi"
                           else [t["name"] for t in body.get("tools") or []])
                    aid = put("api", slugify(d["name"]), {"url": d["url"], "kind": kind, "api_title": (body.get("info") or {}).get("title"),
                                                          "version": str((body.get("info") or {}).get("version") or body.get("openapi") or "") or None,
                                                          "operations": ops}, d["name"], sources[name], {
                              "title": at("/data/name", d["name"]), "url": at("/data/url", d["url"]), "kind": at("/data/kind", kind),
                              "api_title": at("/data/data/info/title", (body.get("info") or {}).get("title")),
                              "version": at("/data/data/info/version", (body.get("info") or {}).get("version")),
                              "operations": at("/data/data/paths" if kind == "openapi" else "/data/data/tools", ops)})
                    apis_by_url[d["url"]] = aid
                    if (rid := route_for(d["url"])):
                        ctx.relate("api", aid, "servedBy", "route", rid, source=sources[name])
                elif kind == "shell":
                    rid = route_for(d["url"])
                    for mn, m in enumerate(body.get("modules") or []):
                        regs = m.get("registrations") or []
                        pm = re.match(r"^/plugins/([^/]+)/", m["module"])
                        plugin = pm.group(1) if pm else "workbench"
                        slug = f"plugin-{slugify(plugin)}" if pm else slugify(m["module"].rsplit("/", 1)[0])
                        pick = lambda k: [{"id": r["id"], "title": r.get("title"), "line": r["line"]} for r in regs if r["kind"] == k]  # noqa: E731
                        p = f"/data/data/modules/{mn}"
                        fields = {"module": m["module"], "plugin": plugin, "views": pick("view"), "menus": pick("menu"),
                                  "commands": pick("command"), "widgets": pick("widget"), "sha256": m.get("sha256")}
                        ev = {k: at(f"{p}/registrations", [r["quote"] for r in regs if r["kind"] == k[:-1]][:6]) for k in ("views", "menus", "commands", "widgets")}
                        ev.update({"title": at(f"{p}/module", m["module"]), "module": at(f"{p}/module", m["module"]),
                                   "plugin": at(f"{p}/module", m["module"]), "sha256": at(f"{p}/sha256", m.get("sha256"))})
                        uid = put("ui", slug, fields, m["module"], sources[name], ev)
                        if rid:
                            ctx.relate("ui", uid, "servedBy", "route", rid, source=sources[name])
            loaded = [(name, snapd(s).get("data")) for name, s in snaps.items() if snapd(s).get("kind") == "plugins"]
            extractors = [x for name, s in snaps.items() if snapd(s).get("kind") == "extractors" for x in (s["data"].get("data") or [])]
            ctypes = [x for name, s in snaps.items() if snapd(s).get("kind") == "content-types" for x in (s["data"].get("data") or [])]
            plugin_ids = {}
            for name, body in loaded:
                for pn, pl in enumerate((body or {}).get("plugins") or []):
                    exs = [x["key"] for x in extractors if x.get("plugin") == pl["id"]]
                    tys = [t["id"] for t in ctypes if t.get("plugin") == pl["id"]]
                    p = f"/data/data/plugins/{pn}"
                    plugin_ids[pl["id"]] = put("plugin", slugify(pl["id"]), {"version": pl.get("version"), "server": pl.get("server"),
                                                                            "content_types": tys, "extractors": exs, "error": pl.get("error")},
                                               pl["id"], sources[name], {
                        "title": at(f"{p}/id", pl["id"]), "version": at(f"{p}/version", pl.get("version")), "server": at(f"{p}/server", pl.get("server")),
                        "error": at(f"{p}/error", pl.get("error")),
                        "content_types": {"quote": ", ".join(tys)[:300], "span": {"pointer": "/data/data", "snapshot": "content types, by plugin"}},
                        "extractors": {"quote": ", ".join(exs)[:300], "span": {"pointer": "/data/data", "snapshot": "extractors, by plugin"}}})

            # Claude Code's connections, to the APIs observed above
            for n, s in enumerate(cc.get("mcp_servers") or []):
                p = f"/data/mcp_servers/{n}"
                fields = {"client": "claude-code", "file": s.get("file"), "transport": s.get("type"), "url": s.get("url"),
                          "command": s.get("command"), "auth": s.get("auth"), "env_names": s.get("env_names") or None}
                ev = {k: at(f"{p}/{'type' if k == 'transport' else k}", v) for k, v in fields.items()}
                ev["title"] = at(f"{p}/name", s["name"])
                kid = put("connection", slugify(f"claude-code-{s['name']}"), fields, s["name"], sources["claude-code"], ev)
                if s.get("url") in apis_by_url:
                    ctx.relate("connection", kid, "connectsTo", "api", apis_by_url[s["url"]], source=sources["claude-code"])

            # Morphogen's cells
            for name, snap in snaps.items():
                d = snapd(snap)
                if not name.startswith("command-") or d.get("kind") != "morphogen":
                    continue
                for n, c in enumerate((d.get("data") or {}).get("cells") or []):
                    kind, _, rest = c["cell"].partition(":")
                    cname = rest.split("/")[-1]
                    p = f"/data/data/cells/{n}"
                    cid = put("cell", slugify(f"{kind}-{cname}"), {"ref": c["cell"], "role": c.get("role"), "owner": c.get("owner"),
                                                                  "ready": c.get("ready"), "cell_source": c.get("source")}, c["cell"], sources[name], {
                        "title": at(f"{p}/cell", c["cell"]), "ref": at(f"{p}/cell", c["cell"]), "role": at(f"{p}/role", c.get("role")),
                        "owner": at(f"{p}/owner", c.get("owner")), "ready": at(f"{p}/ready", c.get("ready")),
                        "cell_source": at(f"{p}/source", c.get("source"))})
                    if (target := components.get(slug_for(kind, cname))):
                        ctx.relate("cell", cid, "cellOf", "component", target, source=sources[name])

        for typ in ("host", "container", "image", "volume", "setting", "route", "api", "plugin", "ui", "connection", "cell"):
            ctx.done(typ)
        ctx.log(", ".join(f"{n} {t}" for t, n in sorted(counts.items())) + f" from {len(hosts)} host(s)")

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
    wb.extractor("observed", observed, "the snapshots observe.py wrote (.state/observed): the host, its containers, images, volumes, "
                 "setting names, routes, APIs, plugins, UIs, connections and Morphogen's cells")
    wb.extractor("drift", drift, "what the map declares against what the repository has; each difference to the review lane")
