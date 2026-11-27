"""The environment's review lane (S-219): a proposed action waits in the kernel's review lane, so a person approves
in one place, the desktop's Review.

    python3 -m environment.review [--once]     # the kernel module's service (compose `environment`), in the kernel's image

For each action waiting for a person (env.review_waiting), it submits one change set in the review lane, keyed
`environment:action:<id>`: a sosa:Actuation with its actuator (sosa:madeByActuator), its caller (as:actor, when the
caller is a kernel agent), a label, and its input in full (dcterms:description). The kernel validates it and holds it
for a reviewer. Once a person has approved it (the kernel applies it, so the approved request is kept as claims) or
rejected it, the module records that person's decision on the action with env.decide: approved, it is queued for its
actuator; rejected, it never is. The kernel refuses a change set's approval by its submitter (this module); the
environment refuses a proposal's approval by its caller, so a person who approved their own request has it refused here,
with the reason.

It wakes on `env_action` (a new proposal) and `kernel_change_set` (an applied approval), and looks again every
KK_SWEEP_SECONDS (default 5), since a rejection sends no notification. It runs as kkm_environment: DATABASE_URL is the
kernel's login (kk_authenticator), KK_ROLE the module's role (the kernel's kk.lib, as every kernel module).
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys

from kk.lib import connect, listen, run, submit

MODULE = "urn:kk:module:environment"
AGENT = "urn:kk:agent:environment"
SCOPE = "urn:kk:scope:default"
ROLE = "kkm_environment"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
LABEL = "http://www.w3.org/2000/01/rdf-schema#label"
DESCRIPTION = "http://purl.org/dc/terms/description"
SOSA = "http://www.w3.org/ns/sosa/"
ACTOR = "https://www.w3.org/ns/activitystreams#actor"


def key(action: int) -> str:
    return f"environment:action:{action}"


def iri(action: int) -> str:
    return f"urn:kk:environment:action:{action}"


def what(a: dict) -> str:
    """The action in a few words: an MCP tool by its exposed name, else the actuator."""
    inp = a["input"] if isinstance(a["input"], dict) else {}
    if a["actuator"].startswith("mcp.") and inp.get("server") and inp.get("tool"):
        return f"{inp['server']}_{inp['tool']}"
    return a["actuator"]


def ops(a: dict, actor: str | None) -> list[dict]:
    """The change set's claims about one waiting action: what the reviewer reads in Review."""
    s, ref = iri(a["id"]), [{"source_uri": iri(a["id"])}]
    shown = a["input"].get("arguments", a["input"]) if isinstance(a["input"], dict) else a["input"]

    def claim(p, o):
        return {"op": "add_claim", "subject": s, "predicate": p, "object": o, "evidence_type": "deterministic",
                "references": ref}
    out = [claim(RDF_TYPE, {"entity": SOSA + "Actuation"}),
           claim(LABEL, {"value": {"@value": f"{what(a)}, asked by {a['caller']} (action {a['id']})"}}),
           claim(SOSA + "madeByActuator", {"entity": f"urn:kk:environment:actuator:{a['actuator']}"}),
           claim(DESCRIPTION, {"value": {"@value": json.dumps(shown, ensure_ascii=False, sort_keys=True)}})]
    if actor:
        out.append(claim(ACTOR, {"entity": actor}))
    return out


def one_pass(conn) -> dict:
    """Submit what waits and is not in the review lane yet; record what a person decided there. Returns what it did."""
    did = {"submitted": [], "approved": [], "rejected": [], "refused": [], "waiting": [], "stuck": []}
    with conn.cursor() as cur:
        cur.execute("select id, actuator, description, input, caller, login, at from env.review_waiting()")
        cols = [d.name for d in cur.description]
        waiting = [dict(zip(cols, r)) for r in cur.fetchall()]
        if not waiting:
            return did
        cur.execute("select idempotency_key, status, decided_by, coalesce(review_note, '') from api.change_sets "
                    "where idempotency_key = any(%s) and attributed_to = %s", ([key(a["id"]) for a in waiting], AGENT))
        sets = {k: (st, by, note) for k, st, by, note in cur.fetchall()}
        cur.execute("select db_role::text, iri from kernel.agent where db_role::text = any(%s)",
                    (sorted({a["caller"] for a in waiting}),))
        agents = dict(cur.fetchall())
        for a in waiting:
            st, by, note = sets.get(key(a["id"]), (None, None, ""))
            if st is None:
                with run(cur, MODULE, {"action": a["id"], "actuator": a["actuator"]}) as (run_id, outputs):
                    got = submit(cur, {"idempotency_key": key(a["id"]), "attributed_to": AGENT, "target_scope": SCOPE,
                                       "lane": "review", "ops": ops(a, agents.get(a["caller"]))}, run_id)
                    outputs.update(change_set=got["id"])
                did["submitted"].append(a["id"])
            elif st in ("approved", "applied", "rejected"):
                approve = st != "rejected"
                if approve and by == a["caller"]:
                    cur.execute("select env.decide(%s, false, %s, %s)", (a["id"], ROLE,
                                f"approved in the review lane by {by}, who asked for it; a proposal needs another person"))
                    did["refused"].append(a["id"])
                    continue
                cur.execute("select env.decide(%s, %s, %s, %s)", (a["id"], approve, by, note or None))
                did["approved" if approve else "rejected"].append(a["id"])
            elif st in ("invalid", "conflict"):
                did["stuck"].append(a["id"])      # the kernel would not hold it for review; logged, left waiting
            else:
                did["waiting"].append(a["id"])
    return did


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Proposed actions into the kernel's review lane, and its decisions back.")
    ap.add_argument("--once", action="store_true", help="one pass, print what it did and exit")
    a = ap.parse_args(argv)
    conn = connect(os.environ.get("KK_ROLE", ROLE))
    if a.once:
        print(json.dumps(one_pass(conn)))
        return 0
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))   # PID 1 in its container: stop at once when compose stops it
    conn.execute("listen env_action")                    # a new proposal wakes it as well as an applied change set

    def step(c):
        did = one_pass(c)
        if any(v for k, v in did.items() if k != "waiting"):
            print(json.dumps(did), flush=True)
    listen(conn, step, sweep=float(os.environ.get("KK_SWEEP_SECONDS") or 5))
    return 0


if __name__ == "__main__":
    sys.exit(main())
