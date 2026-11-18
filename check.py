"""Substrate's one check (S-162): is the map well formed, and does every piece of evidence still say what it said?

    python3 check.py            # check the map; exit 1 on any problem
    python3 check.py --stamp    # fill in `sha256:new` on evidence just written, then check

Standard library only, so it reads the map's YAML by line rather than parsing it: every entity file is one
document in the shape the map skill writes (docs/seed.md, "The map format"). Morphogen's Backstage loader parses
the same files properly when it judges.

Evidence is an annotation whose value is `PATH#Lstart-end sha256:HASH`: the hash of those lines of that file in
this repository, each line's trailing spaces dropped. When the lines change, the hash no longer matches and the
claim the annotation backs is stale until someone re-reads the source and re-cites it. A URL source
(`https://...`) carries a date instead of a hash (`https://example.com/page 2026-11-18`) and is not re-fetched.
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ROOT_FILE = ROOT / "catalog-info.yaml"
KINDS = {"Component", "System", "Domain", "API", "Resource", "Location", "Group", "Role", "Goal"}
NAMESPACES = {"blueprint", "described", "observed"}
NAME = re.compile(r"^[a-zA-Z0-9]+([-_.][a-zA-Z0-9]+)*$")
EVIDENCE = re.compile(r"^\s+(openreplicant\.com/evidence[-a-zA-Z0-9_.]*):\s*\"?(.+?)\"?\s*$")
FILE_SOURCE = re.compile(r"^(?P<path>[^#\s]+)#L(?P<a>\d+)(?:-(?P<b>\d+))?\s+sha256:(?P<hash>[0-9a-f]{12}|new)$")
URL_SOURCE = re.compile(r"^https?://\S+\s+\d{4}-\d{2}-\d{2}$")
REF = re.compile(r"\b(component|api|resource|system|domain|group|role|goal):(?:([a-z]+)/)?([a-zA-Z0-9][-a-zA-Z0-9_.]*)")


def lines_hash(path: Path, a: int, b: int) -> str | None:
    if not path.is_file():
        return None
    lines = path.read_text().splitlines()
    if b > len(lines) or a < 1:
        return None
    return hashlib.sha256("\n".join(l.rstrip() for l in lines[a - 1:b]).encode()).hexdigest()[:12]


def field(text: str, key: str, indent: int) -> str | None:
    m = re.search(rf"^{' ' * indent}{key}:\s*(\S.*?)\s*$", text, re.M)
    return m.group(1).strip("\"'") if m else None


def main(stamp: bool) -> int:
    problems: list[str] = []
    if not ROOT_FILE.is_file():
        print("no catalog-info.yaml")
        return 1
    targets = re.findall(r"^\s+-\s+(\./\S+\.yaml)\s*$", ROOT_FILE.read_text(), re.M)
    files = [ROOT / t for t in targets]
    listed = {f.resolve() for f in files}
    for f in sorted((ROOT / "map").rglob("*.yaml")):
        if f.resolve() not in listed:
            problems.append(f"{f.relative_to(ROOT)}: not a target of catalog-info.yaml")
    entities: dict[tuple[str, str, str], Path] = {}
    texts: dict[Path, str] = {}
    for f in files:
        if not f.is_file():
            problems.append(f"catalog-info.yaml: target {f.relative_to(ROOT)} does not exist")
            continue
        text = f.read_text()
        texts[f] = text
        rel = f.relative_to(ROOT)
        if "\n---" in text.strip():
            problems.append(f"{rel}: one entity per file")
        api, kind = field(text, "apiVersion", 0), field(text, "kind", 0)
        name, ns = field(text, "name", 2), field(text, "namespace", 2)
        if kind not in KINDS:
            problems.append(f"{rel}: kind {kind!r} is not one the map uses")
            continue
        want_api = "openreplicant.com/v1alpha1" if kind in ("Role", "Goal") else "backstage.io/v1alpha1"
        if api != want_api:
            problems.append(f"{rel}: {kind} takes apiVersion {want_api}, not {api}")
        if not name or len(name) > 63 or not NAME.match(name):
            problems.append(f"{rel}: metadata.name {name!r} is not a Backstage name")
        if ns not in NAMESPACES:
            problems.append(f"{rel}: metadata.namespace must be one of {sorted(NAMESPACES)}, not {ns!r}")
        key = (kind.lower(), ns or "", name or "")
        if key in entities:
            problems.append(f"{rel}: {kind} {ns}/{name} is also in {entities[key].relative_to(ROOT)}")
        entities[key] = f
    for f, text in texts.items():
        rel = f.relative_to(ROOT)
        ns = field(text, "namespace", 2) or ""
        spec = text.split("\nspec:", 1)[1] if "\nspec:" in text else ""
        for kind, rns, name in REF.findall(spec):
            if (kind, rns or ns, name) not in entities:
                problems.append(f"{rel}: refers to {kind}:{(rns + '/') if rns else ''}{name}, which is not in the map")
        out = []
        for line in text.splitlines():
            m = EVIDENCE.match(line)
            if m:
                value = m.group(2)
                fm = FILE_SOURCE.match(value)
                if fm:
                    a, b = int(fm["a"]), int(fm["b"] or fm["a"])
                    now = lines_hash(ROOT / fm["path"], a, b)
                    if now is None:
                        problems.append(f"{rel}: {m.group(1)}: {fm['path']} has no lines {a}-{b}")
                    elif fm["hash"] == "new" and stamp:
                        line = line.replace("sha256:new", f"sha256:{now}")
                    elif fm["hash"] == "new":
                        problems.append(f"{rel}: {m.group(1)}: not stamped yet (python3 check.py --stamp)")
                    elif fm["hash"] != now:
                        problems.append(f"{rel}: {m.group(1)}: STALE, {fm['path']} lines {a}-{b} have changed; re-read and re-cite")
                elif not URL_SOURCE.match(value):
                    problems.append(f"{rel}: {m.group(1)}: evidence must be 'PATH#La-b sha256:HASH' or 'URL YYYY-MM-DD'")
            out.append(line)
        if stamp:
            f.write_text("\n".join(out) + "\n")
    for p in problems:
        print(p)
    print(f"{len(entities)} entities, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main("--stamp" in sys.argv[1:]))
