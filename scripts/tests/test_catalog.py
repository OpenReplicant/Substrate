"""Substrate's catalog and its check (S-176). No database: catalog files in a temporary folder.
It should:
- pass on the repository's own catalog/ against deploy/compose.yaml
- report an API nobody provides, an API referenced with no entry, a reference to no entity
- report a compose service with no entry, and an entry naming a service compose does not have
- list what each component uses to provide what
- refuse an entity defined twice

    python3 scripts/tests/test_catalog.py
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import catalog as C  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print(("ok  " if ok else "FAIL"), name, "" if ok else detail)


def ent(kind, name, spec=None, annotations=None):
    md = {"name": name, **({"annotations": annotations} if annotations else {})}
    import yaml
    return yaml.safe_dump({"apiVersion": "backstage.io/v1alpha1", "kind": kind, "metadata": md, "spec": spec or {}})


def folder(files: dict) -> Path:
    d = Path(tempfile.mkdtemp())
    for n, text in files.items():
        (d / n).write_text(text)
    return d


def main():
    ents = C.load(ROOT / "catalog")
    problems = C.check(ents, ROOT / "deploy/compose.yaml")
    check("the repository's catalog fits and matches compose", problems == [], problems)
    check("it describes its components and their APIs", sum(k == "component" for k, _ in ents) >= 10 and sum(k == "api" for k, _ in ents) >= 10)
    check("the gateway is listed as using the model servers to provide the chat API",
          any(n == "gateway" and "llama-chat-slow" in ins and "model-chat" in outs for n, ins, outs in C.translators(ents)))

    base = {"system.yaml": ent("System", "s", {"owner": "group:o"}), "group.yaml": ent("Group", "o", {"type": "team"})}
    d = folder({**base,
                "a.yaml": ent("Component", "a", {"owner": "o", "system": "s", "consumesApis": ["x"], "dependsOn": ["resource:db"]},
                              {"substrate.dev/compose-service": "a"}),
                "b.yaml": ent("Component", "b", {"owner": "o", "system": "s", "providesApis": ["y"]},
                              {"substrate.dev/compose-service": "gone"}),
                "x.yaml": ent("API", "x", {"type": "openapi", "owner": "o", "system": "s"})})
    compose = d / "compose.yaml"
    compose.write_text("services:\n  a: {image: a}\n  extra: {image: e}\n")
    p = C.check(C.load(d), compose)
    check("an API nobody provides is a gap, with who consumes it", any("gap: no component provides API x, consumed by a" in m for m in p), p)
    check("an API referenced with no entry is reported", any("API y is referenced" in m for m in p), p)
    check("a reference to no entity is reported", any("dependsOn resource:db names no entity" in m for m in p), p)
    check("a compose service with no entry is reported", any("compose service extra has no catalog entry" in m for m in p), p)
    check("an entry naming a service compose does not have is reported", any("names compose service gone" in m for m in p), p)

    twice = folder({"one.yaml": ent("API", "x"), "two.yaml": ent("API", "x")})
    try:
        C.load(twice)
        check("an entity defined twice is refused", False)
    except SystemExit as e:
        check("an entity defined twice is refused", "defined twice" in str(e), e)

    print(f"{sum(checks)}/{len(checks)} checks passed")
    sys.exit(0 if all(checks) else 1)


if __name__ == "__main__":
    main()
