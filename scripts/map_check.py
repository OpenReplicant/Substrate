"""Step 2's state in kernel (S-33), for scripts/check.sh: the catalog's claims, the calls observed in the last
hour, and the gaps waiting in the review lane. Runs in the tools container with KK_ADMIN_URL (kernel's superuser,
read only here). Exits 1 when the catalog is not in kernel yet."""
import os
import sys

import psycopg

with psycopg.connect(os.environ["KK_ADMIN_URL"]) as conn:
    one = lambda q: conn.execute(q).fetchone()[0]  # noqa: E731
    stated = one("select count(*) from api.claims where attributed_to = 'urn:kk:agent:encoder-backstage'"
                 " and status <> 'deprecated'")
    calls = one("select count(distinct (subject, object_entity)) from api.claims where evidence_type = 'observed'"
                " and predicate = 'https://w3id.org/knowledge-kernel/tosca#connectsTo' and valid_to >= now() - interval '1 hour'")
    waiting = one("select count(*) from api.change_sets where attributed_to = 'urn:kk:agent:map-drift'"
                  " and status = 'awaiting_review'")
print(f"{stated} claims from catalog-info.yaml, {calls} calls observed in the last hour, {waiting} gaps awaiting review")
sys.exit(0 if stated else 1)
