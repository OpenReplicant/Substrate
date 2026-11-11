#!/usr/bin/env python3
"""Spec step 24's queries: recall judged on substrate's own history, not on a public benchmark.

Each row of DECISIONS.md that quotes the owner gives one query: the owner's words. Its relevant items are the
parts of the map the row's body names (a component, skill, hook, choice or candidate, by its slug, written as a
hyphenated name or in backticks). The owner's words seldom name the part, so finding it takes meaning, not
spelling. Rows with an odd S-number are held out (verdicts only); even ones are the search set (tuning). Every commit on
main gives another: its subject (less any step number or decision id) is the query, and the parts whose files it
changed are relevant; a commit whose hash starts with an odd hex digit is held out.

    bin/in-tools python3 scripts/trials/recall/queries.py      # writes .state/trials/recall/queries.json
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TYPES = ("component", "skill", "hook", "choice", "candidate")
GENERIC = {"workbench", "scripts", "tools", "secrets", "runtime", "skills", "ui", "kernel", "morphogen",
           "postgres", "sandbox", "recall", "vocabulary", "observer", "reasoner"}


def items(conn) -> tuple[dict[str, tuple[str, str]], list[tuple[str, tuple[str, str]]]]:
    """(slug -> (type, id), [(a path glob a part may change, its (type, id))])."""
    out, globs = {}, []
    for t in TYPES:
        for slug, iid in conn.execute(f"select slug, id from api.{t} where wb.live(id)").fetchall():
            out[slug] = (t, str(iid))
    for iid, change in conn.execute("""select id, annotations->>'morphogen.dev/change' from api.component
                                        where wb.live(id) and annotations ? 'morphogen.dev/change'""").fetchall():
        for g in (change or "").split():
            globs.append((g, ("component", str(iid))))
    return out, globs


def rows(text: str):
    for line in text.splitlines():
        m = re.match(r"\| (S-\d+) \| (.*) \| (\w[\w ]*) \|$", line)
        if m:
            yield m.group(1), m.group(2)


def main() -> None:
    import psycopg
    url = os.environ.get("RECALL_DB") or sys.exit("RECALL_DB: a login to the workbench database")
    import fnmatch
    with psycopg.connect(url) as conn:
        known, globs = items(conn)
    queries = []
    for sid, body in rows((ROOT / "DECISIONS.md").read_text()):
        quotes = [q for q in re.findall(r'"([^"]{12,})"', body.split("**", 2)[-1][:1200])
                  if len(q.split()) >= 6 and not q.startswith(("http", "/", "env."))][:3]
        if not quotes:
            continue
        rest = re.sub(r'"[^"]*"', " ", body)            # what the row says beside the owner's words
        rel = set()
        for slug, ref in known.items():
            if slug in GENERIC or len(slug) < 4:
                continue
            if ("-" in slug and re.search(rf"(?<![\w-]){re.escape(slug)}(?![\w-])", rest)) or f"`{slug}`" in rest:
                rel.add(ref)
        for path in re.findall(r"`([\w./*-]+/[\w./*-]+)`", rest):
            for g, ref in globs:
                if fnmatch.fnmatch(path, g) or fnmatch.fnmatch(path.rstrip("/") + "/x", g):
                    rel.add(ref)
        if rel:
            n = int(sid[2:])
            queries.append({"id": sid, "split": "held-out" if n % 2 else "search", "query": " ".join(quotes),
                            "relevant": sorted(list(r) for r in rel)})
    # every commit on main: its subject is the query; the parts whose files it changed are what it concerns
    import subprocess
    log = subprocess.run(["git", "log", "--first-parent", "--no-merges", "--format=%x1e%H%x1f%s", "--name-only", "main"],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout
    for entry in log.split("\x1e")[1:]:
        head, _, files = entry.partition("\n")
        sha, _, subject = head.partition("\x1f")
        subject = re.sub(r"^spec step \d+:\s*", "", subject)
        subject = re.sub(r"\s*\((S-\d+[^)]*)\)\s*$", "", subject)
        if len(subject.split()) < 4:
            continue
        rel = set()
        for f in (x for x in files.splitlines() if x.strip()):
            for g, ref in globs:
                if fnmatch.fnmatch(f, g):
                    rel.add(ref)
        if rel and len(rel) <= 8:
            queries.append({"id": sha[:10], "split": "held-out" if int(sha[0], 16) % 2 else "search", "query": subject,
                            "relevant": sorted(list(r) for r in rel), "from": "commit"})
    out = ROOT / ".state/trials/recall/queries.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(queries, indent=1))
    split = {s: sum(q["split"] == s for q in queries) for s in ("search", "held-out")}
    print(f"{len(queries)} queries ({split['search']} search, {split['held-out']} held out), "
          f"{sum(len(q['relevant']) for q in queries)} relevant items in all")


if __name__ == "__main__":
    main()
