"""The environment as a kernel module (S-219): a proposed action waits in the kernel's review lane and a person's
decision there is the action's. In a throwaway kernel with the environment's schema beside it (ADMIN_URL from
scripts/test.sh; it runs in the kernel's image). It should:
- install through the kernel's module contract (`kk module install environment`): its manifest checked, its role and
  agent made, and installing again changing nothing
- submit each waiting action once, as a change set in the review lane that the kernel holds for a reviewer, saying
  what is asked, by whom, of which actuator, with its input in full; an MCP tool by the name its caller used
- record a person's approval there on the action (queued for its actuator, decided by that person), and keep the
  approved request as claims
- record a rejection (refused, with the reviewer's note), and refuse a proposal its own caller approved
- leave the decision to the module: the MCP router may no longer decide; the module may decide, and do nothing else
  in the environment

    scripts/test.sh scripts/tests/test_review.py
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(Path(__file__).resolve().parent), str(ROOT)]
import kernelfx  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print(("ok  " if ok else "FAIL"), name, "" if ok else detail)


def main():
    k = None
    try:
        k = kernelfx.Kernel(os.environ["ADMIN_URL"])
        run(k)
    except Exception as e:                                  # a missing kernel is a failure, named
        checks.append(False)
        print("FAIL the review lane:", type(e).__name__, e)
    finally:
        if k:
            k.close()
    print(f"{sum(checks)}/{len(checks)} checks passed")
    sys.exit(0 if all(checks) else 1)


def kk(k, *args):
    out = subprocess.run([sys.executable, "-m", "kk", *args], env=k.env, capture_output=True, text=True)
    if out.returncode:
        raise RuntimeError(f"kk {' '.join(args)}: {out.stderr.strip()[-400:]}")
    return json.loads(out.stdout.strip().splitlines()[-1])


def status(admin, cs_key, want, seconds=30):
    with psycopg.connect(admin, autocommit=True) as c:
        for _ in range(seconds * 4):
            r = c.execute("select status from kernel.change_set where idempotency_key = %s", (cs_key,)).fetchone()
            if r and r[0] in want:
                return r[0]
            time.sleep(0.25)
    return r and r[0]


def run(k):
    from environment import Env
    from environment import db as envdb
    from environment.review import one_pass
    from kk.lib import connect

    with psycopg.connect(k.admin, autocommit=True) as c:
        envdb.migrate(c)
    with tempfile.TemporaryDirectory() as out:
        first = kk(k, "module", "install", str(ROOT / "environment"), "--out", out)
        again = kk(k, "module", "install", str(ROOT / "environment"), "--out", out)
    check("installs through the kernel's module contract", first.get("module") == "urn:kk:module:environment"
          and first.get("migration") == "applied", first)
    check("and installing again applies nothing", again.get("migration", "").startswith("skipped"), again)
    kk(k, "agent", "add", "assistant", "--no-login")
    kk(k, "person", "add", "tester", "--no-login")

    admin = psycopg.connect(k.admin, autocommit=True)
    e = Env(admin)
    with admin.transaction():
        agent = admin.execute("select iri, db_role from kernel.agent where iri = 'urn:kk:agent:environment'").fetchone()
    check("its agent and role are the kernel's", agent == ("urn:kk:agent:environment", "kkm_environment"), agent)
    priv = admin.execute("select has_function_privilege('env_router', 'env.decide(bigint,boolean,text,text)', 'execute'), "
                         "has_function_privilege('kkm_environment', 'env.decide(bigint,boolean,text,text)', 'execute'), "
                         "has_function_privilege('kkm_environment', 'env.act(text,jsonb,text)', 'execute'), "
                         "has_function_privilege('kkm_environment', 'env.actuator(text,text,text,text)', 'execute')").fetchone()
    check("the router may no longer decide; the module may, and may not act or set a gate", priv == (False, True, False, False), priv)

    q = e.actuator("shop.refund", "propose", "person_owner", "Refund an order")
    a1, st1 = e.act("shop.refund", {"order": 1042, "amount_eur": 30}, "agent_assistant")
    a2, _ = e.act("shop.refund", {"order": 77, "amount_eur": 9000}, "agent_assistant")
    a3, _ = e.act("shop.refund", {"order": 5, "amount_eur": 1}, "person_tester")
    admin.execute("select * from env.mcp_register('crm', 'http', '{}', '{}', %s::jsonb, 'connector:crm')",
                  (json.dumps([{"name": "update_contact", "annotations": {}}]),))
    a4, st4 = admin.execute("select * from env.mcp_call('crm_update_contact', %s, 'agent_assistant')",
                            (json.dumps({"id": 3, "email": "a@example.org"}),)).fetchone()
    check("four actions wait for a person", (st1, st4) == ("proposed", "proposed"), (st1, st4))

    mod = connect("kkm_environment", url=k.url)
    did = one_pass(mod)
    check("one pass submits each waiting action to the review lane", sorted(did["submitted"]) == sorted([a1, a2, a3, a4]), did)
    held = status(k.admin, f"environment:action:{a1}", {"awaiting_review"})
    check("the kernel holds it for a reviewer", held == "awaiting_review", held)
    for a in (a2, a3, a4):
        status(k.admin, f"environment:action:{a}", {"awaiting_review"})
    check("a second pass submits nothing again", one_pass(mod)["submitted"] == [])

    with admin.transaction():
        admin.execute("set local role person_owner")
        queue = {r[0]: r[1] for r in admin.execute(
            "select c.idempotency_key, q.ops from api.review_queue q join kernel.change_set c on c.id = q.id")}
    ops = queue.get(f"environment:action:{a1}") or []
    said = {o["predicate"].rsplit("/", 1)[-1].rsplit("#", 1)[-1]: o["object"] for o in ops}
    check("Review shows the request: an actuation, by its actuator", said.get("type", {}).get("entity") == "http://www.w3.org/ns/sosa/Actuation"
          and said.get("madeByActuator", {}).get("entity") == "urn:kk:environment:actuator:shop.refund", said)
    check("who asked, as the kernel's agent", said.get("actor", {}).get("entity") == "urn:kk:agent:assistant", said)
    check("and its input in full", json.loads(said.get("description", {}).get("value", {}).get("@value", "null"))
          == {"order": 1042, "amount_eur": 30}, said)
    lab4 = next((o["object"]["value"]["@value"] for o in queue.get(f"environment:action:{a4}") or []
                 if o["predicate"].endswith("label")), "")
    check("an MCP tool is named as its caller called it", lab4.startswith("crm_update_contact, asked by agent_assistant"), lab4)

    def review(action, approve, who, note=None):
        with admin.transaction():
            cs = admin.execute("select id from kernel.change_set where idempotency_key = %s", (f"environment:action:{action}",)).fetchone()[0]
            admin.execute(f"set local role {who}")
            return admin.execute("select api.review(%s, %s, %s)", (cs, approve, note)).fetchone()[0]

    check("a person approves it in the review lane: the kernel applies it", review(a1, True, "person_owner") == "applied")
    review(a2, False, "person_owner", "too much; call the customer")
    review(a3, True, "person_tester")
    did = one_pass(mod)
    check("the module records each decision", (did["approved"], did["rejected"], did["refused"]) == ([a1], [a2], [a3]), did)
    row = admin.execute("select status, decided_by from env.action where id = %s", (a1,)).fetchone()
    msgs = e.read(q, 0)
    check("approved: queued for its actuator, decided by that person", row == ("queued", "person_owner")
          and [m["action"] for m in msgs] == [a1], (row, msgs))
    kept = admin.execute("select count(*) from kernel.claim where subject = %s", (f"urn:kk:environment:action:{a1}",)).fetchone()[0]
    check("and the approved request is kept as claims", kept == 5, kept)
    row = admin.execute("select status, decided_by, reason from env.action where id = %s", (a2,)).fetchone()
    check("rejected: refused, with the reviewer's note", row == ("refused", "person_owner", "too much; call the customer"), row)
    row = admin.execute("select status, reason from env.action where id = %s", (a3,)).fetchone()
    check("approved by its own caller: refused, saying why", row[0] == "refused" and "who asked for it" in (row[1] or ""), row)
    check("the MCP call still waits, nothing else changed", one_pass(mod)["waiting"] == [a4]
          and e.status(a4) == "proposed")
    mod.close()
    admin.close()


if __name__ == "__main__":
    main()
