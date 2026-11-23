"""Substrate's catalog (S-176): its parts as Backstage entity files in catalog/, one per entity, which the kernel reads
with encoder-backstage (the kernel's D-100). This script checks them, without the kernel:

- **fit**: every API a component consumes has a provider; every API is provided by someone; every reference
  (providesApis, consumesApis, dependsOn, owner, system) names an entity that exists;
- **what uses what**: each component that uses some APIs to provide others (the gateway uses llama-server's API to
  provide its own chat API, a translator; the voice head uses several to provide its page); where two parts share no
  API, a translator from the catalog has to go between them;
- **compose**: the catalog against deploy/compose.yaml, both ways: a service with no entry, an entry naming a service
  compose does not have;
- **kernel** (`--kernel`): the same fit read from the kernel's claims (what `scripts/kernel.sh catalog` put there, through
  the read model, under its own role), and the drift between the files and the kernel: a provides or consumes in one
  and not the other (a file changed and not yet encoded).

    bin/in-tools python3 scripts/catalog.py check [--compose deploy/compose.yaml] [--kernel]
    bin/in-tools python3 scripts/catalog.py apis          # each API with its providers and consumers

Exit 1 when a check fails. Needs PyYAML (the tools container has it).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ANN = "substrate.dev/"


def load(directory: Path) -> dict[tuple[str, str], dict]:
    """(kind, name) -> entity, lower-cased kind; every document of every *.yaml file."""
    out: dict[tuple[str, str], dict] = {}
    for f in sorted(directory.glob("*.yaml")):
        for doc in yaml.safe_load_all(f.read_text(encoding="utf-8")):
            if not isinstance(doc, dict) or "kind" not in doc:
                continue
            key = (doc["kind"].lower(), doc["metadata"]["name"])
            if key in out:
                raise SystemExit(f"{f.name}: {key[0]}:{key[1]} is defined twice")
            doc["_file"] = f.name
            out[key] = doc
    return out


def ref(r: str, default_kind: str) -> tuple[str, str]:
    """A Backstage entity reference: [kind:][namespace/]name."""
    kind, _, name = r.rpartition(":")
    return (kind or default_kind).lower(), name.split("/")[-1]


def apis(ents: dict) -> dict[str, dict[str, list[str]]]:
    table = {n: {"providers": [], "consumers": []} for (k, n) in ents if k == "api"}
    for (k, n), e in ents.items():
        if k != "component":
            continue
        for a in e["spec"].get("providesApis") or []:
            table.setdefault(ref(a, "api")[1], {"providers": [], "consumers": []})["providers"].append(n)
        for a in e["spec"].get("consumesApis") or []:
            table.setdefault(ref(a, "api")[1], {"providers": [], "consumers": []})["consumers"].append(n)
    return table


def check(ents: dict, compose: Path | None) -> list[str]:
    problems: list[str] = []
    table = apis(ents)
    for name, t in sorted(table.items()):
        if ("api", name) not in ents:
            problems.append(f"API {name} is referenced ({', '.join(t['providers'] + t['consumers'])}) but has no entry")
        if not t["providers"]:
            who = f", consumed by {', '.join(t['consumers'])}" if t["consumers"] else ""
            problems.append(f"gap: no component provides API {name}{who}")
    for (k, n), e in ents.items():
        spec = e.get("spec") or {}
        for field, default in (("dependsOn", "component"), ("owner", "group"), ("system", "system")):
            vals = spec.get(field)
            for r in ([vals] if isinstance(vals, str) else vals or []):
                if ref(r, default) not in ents:
                    problems.append(f"{k}:{n} ({e['_file']}): {field} {r} names no entity")
    if compose:
        services = set((yaml.safe_load(compose.read_text(encoding="utf-8")).get("services") or {}))
        named = {e["metadata"].get("annotations", {}).get(ANN + "compose-service"): f"{k}:{n}"
                 for (k, n), e in ents.items() if e["metadata"].get("annotations", {}).get(ANN + "compose-service")}
        for s in sorted(services - set(named)):
            problems.append(f"compose service {s} has no catalog entry")
        for s, who in sorted(named.items()):
            if s not in services:
                problems.append(f"{who} names compose service {s}, which {compose.name} does not have")
    # the catalog's root Location (catalog-info.yaml, S-193) names every entity file, so Morphogen and Backstage see all
    files = {e["_file"] for e in ents.values()} - {"catalog-info.yaml"}
    roots = [e for (k, _), e in ents.items() if k == "location" and e["_file"] == "catalog-info.yaml"]
    listed = {t.removeprefix("./") for e in roots for t in (e.get("spec") or {}).get("targets") or []}
    if not roots:
        problems.append("catalog-info.yaml: no Location naming the entity files")
    for f in sorted(files - listed) if roots else []:
        problems.append(f"{f} is not a target of catalog-info.yaml's Location")
    for f in sorted(listed - files):
        problems.append(f"catalog-info.yaml names {f}, which has no entity")
    return problems


BS = "https://w3id.org/knowledge-kernel/backstage#"
SYSTEM = "urn:kk:system:substrate"


def kernel_links() -> set[tuple[str, str, str]]:
    """(component, providesApi|consumesApi, api) for every component part of Substrate's system, from the kernel's
    usable claims, read as the read model's role (as the UI reads them)."""
    import os
    import psycopg
    sys.path[:0] = [str(ROOT / "scripts"), str(ROOT)]
    from db import kernel_url
    from gateway import settings
    url = os.environ.get("KERNEL_URL") or kernel_url(settings())
    with psycopg.connect(url, connect_timeout=10) as c:
        c.execute("set role kkm_view_substrate")
        rows = c.execute(
            "select u.subject, u.predicate, u.object_entity from substrate.usable u where u.predicate = any(%s) and "
            "exists (select 1 from substrate.usable p where p.subject = u.subject and p.predicate = %s and p.object_entity = %s)",
            ([BS + "providesApi", BS + "consumesApi"], BS + "partOf", SYSTEM)).fetchall()
    name = lambda iri: iri.rsplit(":", 1)[-1]                                             # noqa: E731
    return {(name(s), p.rsplit("#", 1)[-1], name(o)) for s, p, o in rows}


def file_links(ents: dict) -> set[tuple[str, str, str]]:
    out = set()
    for (k, n), e in ents.items():
        if k == "component":
            for field, rel in (("providesApis", "providesApi"), ("consumesApis", "consumesApi")):
                out |= {(n, rel, ref(a, "api")[1]) for a in e["spec"].get(field) or []}
    return out


def check_kernel(ents: dict) -> tuple[list[str], int]:
    links = kernel_links()
    problems = []
    provided = {a for _, r, a in links if r == "providesApi"}
    for c, r, a in sorted(links):
        if r == "consumesApi" and a not in provided:
            problems.append(f"kernel: gap: {c} consumes {a}, which no component of the system provides")
    f = file_links(ents)
    for c, r, a in sorted(f - links):
        problems.append(f"drift: the files say {c} {r} {a}; the kernel does not (scripts/kernel.sh catalog)")
    for c, r, a in sorted(links - f):
        problems.append(f"drift: the kernel says {c} {r} {a}; the files do not")
    return problems, len(links)


def translators(ents: dict) -> list[tuple[str, list[str], list[str]]]:
    """Components that provide some APIs by consuming others: the bridges in the map."""
    out = []
    for (k, n), e in sorted(ents.items()):
        if k == "component" and e["spec"].get("providesApis") and e["spec"].get("consumesApis"):
            out.append((n, e["spec"]["consumesApis"], e["spec"]["providesApis"]))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("command", choices=["check", "apis"])
    ap.add_argument("--catalog", default=str(ROOT / "catalog"))
    ap.add_argument("--compose", default=None, help="a compose file to compare with (check)")
    ap.add_argument("--kernel", action="store_true", help="also check the kernel's claims, and their drift from the files")
    a = ap.parse_args()
    ents = load(Path(a.catalog))
    if a.command == "apis":
        for name, t in sorted(apis(ents).items()):
            typ = ents.get(("api", name), {}).get("spec", {}).get("type", "?")
            print(f"{name} [{typ}]: provided by {', '.join(t['providers']) or 'nobody'}; consumed by {', '.join(t['consumers']) or 'nobody'}")
        return
    problems = check(ents, Path(a.compose) if a.compose else None)
    if a.kernel:
        kp, n = check_kernel(ents)
        print(f"kernel: {n} provides and consumes links of {SYSTEM}")
        problems += kp
    kinds = {}
    for (k, _) in ents:
        kinds[k] = kinds.get(k, 0) + 1
    print("catalog: " + ", ".join(f"{v} {k}" for k, v in sorted(kinds.items())))
    for n, ins, outs in translators(ents):
        print(f"  {n} uses {', '.join(ins)} to provide {', '.join(outs)}")
    for p in problems:
        print("  FAIL  " + p)
    print("ok: every consumed API has a provider and every reference resolves" if not problems else f"{len(problems)} problem(s)")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
