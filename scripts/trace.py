"""The chain behind one part, from kernel: what the repository has (observed), what the map declares (intended),
each gap map-drift found between them, and how each gap was decided (spec step 2, S-51). Runs in the tools
container with KK_ADMIN_URL (kernel's superuser, read only here).

    bin/in-tools python3 scripts/trace.py NAME          # e.g. setup, posttooluse-map
    scripts/trace.sh NAME                               # the same, with KK_ADMIN_URL from .env

Exits 1 when kernel knows nothing about the part.
"""
import os
import sys

import psycopg

OA, RDF_TYPE = "http://www.w3.org/ns/oa#", "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
BS, KKT = "https://w3id.org/knowledge-kernel/backstage#", "https://w3id.org/knowledge-kernel/tosca#"
DCT_TYPE = "http://purl.org/dc/terms/type"


def main(name: str) -> int:
    node = f"urn:kk:node:{name}"
    with psycopg.connect(os.environ["KK_ADMIN_URL"]) as conn:
        q = lambda sql, *a: conn.execute(sql, a).fetchall()  # noqa: E731
        observed = q("""select c.id, c.object_entity, s.idempotency_key, c.recorded_at from api.claims c
                        join api.change_sets s on s.id = c.change_set
                        where c.subject = %s and c.predicate = %s and c.attributed_to = 'urn:kk:agent:self-encoder'
                          and c.status <> 'deprecated'""", node, KKT + "nodeType")
        declared = q("""select c.id, c.object_entity, s.idempotency_key, c.recorded_at from api.claims c
                        join api.change_sets s on s.id = c.change_set
                        where c.subject = %s and c.predicate = %s and c.attributed_to = 'urn:kk:agent:encoder-backstage'
                          and c.status <> 'deprecated'""", node, RDF_TYPE)
        # gaps that were decided (their claims applied, then possibly retracted once the gap closed)
        decided = q("""select distinct g.subject, s.id, s.status, s.decided_by, s.decided_at, s.review_note
                       from api.claims t join api.claims g on g.subject = t.subject and g.predicate = %s
                       join api.change_sets s on s.id = g.change_set
                       where t.predicate = %s and t.object_entity = %s and t.subject like 'urn:kk:drift:%%'""",
                    DCT_TYPE, OA + "hasTarget", node)
        statuses = {r[0]: r[1] for r in q("""select subject, string_agg(distinct status::text, ',') from api.claims
                                             where subject like 'urn:kk:drift:%%' group by subject""")}
        texts = {r[0]: r[1] for r in q("""select subject, object_value->>'@value' from api.claims
                                          where predicate = %s and subject like 'urn:kk:drift:%%'""", OA + "bodyValue")}
        # gaps still waiting in the review lane
        waiting = [r for r in q("select id, ops, submitted_at from api.review_queue")
                   if any(o.get("predicate") == OA + "hasTarget" and (o.get("object") or {}).get("entity") == node
                          for o in r[1])]
    if not (observed or declared or decided or waiting):
        print(f"kernel knows nothing about {node}")
        return 1
    print(f"{node}")
    for cid, t, key, at in observed:
        print(f"  observed  claim {cid}  a {t.rsplit(':', 1)[-1]}  ({key.split(':', 2)[-1]}, {at:%Y-%m-%d %H:%M})")
    for cid, t, key, at in declared:
        print(f"  declared  claim {cid}  a {t.rsplit('#', 1)[-1]}  ({key.split(':', 2)[-1]}, {at:%Y-%m-%d %H:%M})")
    for gap, cs, status, by, when, note in decided:
        state = statuses.get(gap, "")
        closed = " - closed since: retracted by map-drift" if "deprecated" in state and "normal" not in state else ""
        print(f"  gap       {gap}  change set {cs}: {status}")
        print(f"            \"{texts.get(gap, '')}\"")
        print(f"            decided by {by} {when:%Y-%m-%d %H:%M}: {note or '(no note)'}{closed}")
    for cs, ops, at in waiting:
        body = next((o["object"]["value"]["@value"] for o in ops if o.get("predicate") == OA + "bodyValue"), "")
        print(f"  gap       change set {cs}: awaiting review since {at:%Y-%m-%d %H:%M}")
        print(f"            \"{body}\"")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1]))
