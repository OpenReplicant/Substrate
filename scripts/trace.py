"""The chain behind one part, from Workbench: what the repository has (observed), what the map declares (intended),
each gap drift raised between them, and how each was decided (spec step 2, S-51). Runs in the tools container.

    scripts/trace.sh NAME          # e.g. setup, posttooluse-map, knowledge-kernel
"""
import json
import os
import sys

import psycopg


def main(name: str) -> int:
    with psycopg.connect(os.environ["WORKBENCH_ADMIN_URL"].rsplit("/", 1)[0] + "/workbench") as conn:
        q = lambda sql, *a: conn.execute(sql, a).fetchall()  # noqa: E731
        observed = q("""select 'skill', s.id, s.path from content.skill s where s.slug = %s
                        union all select 'hook', h.id, h.path from content.hook h where h.slug = %s""", name, name)
        declared = q("select c.id, c.kind, c.type from content.component c where c.slug = %s", name)
        claims = q("""select c.subject_type, c.field, c.author, c.status, c.quote, c.span::text, c.id from wb.claim c
                      where c.subject_id = any(%s::uuid[]) and c.field in ('title', 'type', 'path', 'kind')
                      order by c.observed_at""", [str(r[1]) for r in observed] + [str(r[0]) for r in declared])
        gaps = q("""select d.id, d.key, d.status, d.subject->>'text', d.decided_by, d.decided_at, d.note from wb.decision d
                    where d.key like %s order by d.created_at""", f"%:{name}")
    if not (observed or declared or gaps):
        print(f"Workbench knows nothing about {name}")
        return 1
    print(name)
    for typ, iid, path in observed:
        print(f"  observed  {typ} {iid}  ({path})")
    for iid, kind, typ in declared:
        print(f"  declared  {kind} {typ or ''} {iid}  (catalog-info.yaml)")
    for st, field, author, status, quote, span, cid in claims:
        print(f"    claim {cid}  {st}.{field} by {author}, {status}: {(quote or '').strip()[:60]} {span or ''}")
    for did, key, status, text, by, at, note in gaps:
        print(f"  gap       {did} ({key}): {status}" + (f" by {by} {at:%Y-%m-%d %H:%M}: {note or ''}" if by else ""))
        print(f"            \"{text}\"")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]) if len(sys.argv) == 2 else print(__doc__) or 2)
