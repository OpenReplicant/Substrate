"""Lookup (docs/tasks/rd-pipeline.md, step 4): papers for a described need. Workbench's recall (words, meaning, the graph)
limited to the paper type, then the record's fields beside each hit and the filters applied. No model at query time.

    scripts/workbench.sh run packages/papers/lookup.py "reuse past successful action sequences" [--kind K] [--slot S]
                         [--testable yes|no] [--limit 5] [--json]

--kind and --slot take one value of the record's lists (comma-separated for several). A paper with no record has no kind or
slot, so a kind or slot filter leaves it out. The query is asked for a few hundred papers before the filters cut, so a filter
does not starve the answer. Run inside the tools container with Workbench's settings (scripts/workbench.sh run).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "workbench"))
from workbench import embed  # noqa: E402
from workbench.cli import connect  # noqa: E402

DEPTH = 0       # papers only: the graph walk would only reach listings


def lookup(conn, need: str, kinds=None, slots=None, testable=None, limit: int = 5, pool: int = 300) -> list[dict]:
    hits = embed.recall(conn, need, lim=pool, depth=DEPTH, types=["paper"])
    ids = [h["id"] for h in hits]
    rows = {str(r[0]): r for r in conn.execute(
        "select id, arxiv_id, title, component_kind, slot, testable, listing_count, citations, trial from api.paper where id = any(%s::uuid[])", (ids,))}
    out = []
    for h in hits:
        r = rows.get(h["id"])
        if not r:
            continue
        p = {"arxiv_id": r[1], "title": r[2], "kind": r[3], "slot": r[4], "testable": r[5], "listed_in": r[6], "citations": r[7],
             "trial": r[8], "score": h["score"], "via": h["via"]}
        if (kinds and p["kind"] not in kinds) or (slots and p["slot"] not in slots) or (testable is not None and bool(p["testable"]) != testable):
            continue
        out.append(p)
        if len(out) >= limit:
            break
    return out


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    a.add_argument("need")
    a.add_argument("--kind"); a.add_argument("--slot"); a.add_argument("--testable", choices=["yes", "no"])
    a.add_argument("--limit", type=int, default=5); a.add_argument("--json", action="store_true")
    o = a.parse_args(argv)
    with connect() as conn:
        rows = lookup(conn, o.need, o.kind.split(",") if o.kind else None, o.slot.split(",") if o.slot else None,
                      None if not o.testable else o.testable == "yes", o.limit)
    if o.json:
        print(json.dumps(rows, indent=2))
        return
    for i, p in enumerate(rows, 1):
        print(f"{i}. {p['title']}  [{p['arxiv_id']}]\n   kind {p['kind'] or '-'} | slot {p['slot'] or '-'} | testable {p['testable']} | "
              f"listed in {p['listed_in']} | cited {p['citations'] if p['citations'] is not None else '-'}" + (f" | trial {p['trial']}" if p['trial'] else ""))
    if not rows:
        print("no paper matches")


if __name__ == "__main__":
    main()
