"""The chain behind one part, from Workbench: the item by that name in any content type, the claims behind it, the
relations from it followed outward (who stated each one), the map's parts that say they run as it, and each gap
drift raised about it with its decision (spec steps 2 and 5). Runs in the tools container.

    scripts/trace.sh NAME [DEPTH]   # e.g. setup, substrate-caddy-srv0-wb-api-any, workbench-mcp-tools
"""
import os
import sys

import psycopg


def main(name: str, depth: int = 3) -> int:
    with psycopg.connect(os.environ["WORKBENCH_ADMIN_URL"].rsplit("/", 1)[0] + "/workbench") as conn:
        q = lambda sql, *a: conn.execute(sql, a).fetchall()  # noqa: E731
        types = [r[0] for r in q("select id from wb.content_type order by id")]

        def find(slug=None, iid=None):
            out = []
            for t in types:
                rows = q(f"select id, slug, title from content.{t} where " + ("slug = %s" if slug else "id = %s"), slug or iid)
                out += [(t, *r) for r in rows]
            return out

        def claims(iid):
            return q("""select field, author, quote from wb.claim where subject_id = %s and status = 'current'
                        and field in ('title', 'kind', 'type', 'path', 'image', 'state', 'url', 'upstreams', 'match', 'service')
                        order by field""", iid)

        start = find(slug=name)
        gaps = q("""select d.key, d.status, d.subject->>'text', d.decided_by, d.decided_at, d.note from wb.decision d
                    where d.key like %s and d.status <> 'withdrawn' order by d.created_at""", f"%:{name}")
        if not (start or gaps):
            print(f"Workbench knows nothing about {name}")
            return 1
        seen = set()

        def show(t, iid, slug, title, level, via=""):
            pad = "  " * level
            print(f"{pad}{via}{t} {slug}" + (f"  \"{title}\"" if title and title != slug else ""))
            if (t, str(iid)) in seen:
                return
            seen.add((t, str(iid)))
            for field, author, quote in claims(iid):
                print(f"{pad}    {field} by {author}: {(quote or '').strip()[:90]}")
            if level >= depth:
                return
            for pred, to_type, to_id, author in q("""select predicate, to_type, to_id, author from wb.relation
                                                     where from_type = %s and from_id = %s order by predicate""", t, iid):
                for tt, tid, tslug, ttitle in find(iid=to_id)[:1]:
                    show(tt, tid, tslug, ttitle, level + 1, f"--{pred}--> ({author or 'unattributed'}) ")
            for pred, from_type, from_id, author in q("""select predicate, from_type, from_id, author from wb.relation
                                                         where to_type = %s and to_id = %s order by predicate""", t, iid):
                if pred in ("observedAs", "proxiesTo", "serves", "servedBy"):     # who says they run as it, and what leads to it
                    for ft, fid, fslug, ftitle in find(iid=from_id)[:1]:
                        if (ft, str(fid)) not in seen:
                            show(ft, fid, fslug, ftitle, level + 1, f"<--{pred}-- ({author or 'unattributed'}) ")

        for t, iid, slug, title in start:
            show(t, iid, slug, title, 0)
        for key, status, text, by, at, note in gaps:
            print(f"gap {key}: {status}" + (f" by {by} {at:%Y-%m-%d %H:%M}: {note or ''}" if by else ""))
            print(f"    \"{text}\"")
    return 0


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) == 3 else 3))
