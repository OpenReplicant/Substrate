"""The judge (S-151; docs/framework.md, "The judge is an interface"): a candidate component and the incumbent in,
a verdict out, on cases the candidate's author cannot read. Its first filler is this script, run as its own
database login (env_judge) in its own container (compose service `judge`), with the labelled cases mounted there
only (judge/cases).

    python3 -m environment.judge          # claims proposed components and judges them, forever
    python3 -m environment.judge once     # one, if any is waiting

For the voice head's reply component: every labelled utterance (judge/cases/voice_reply.jsonl), the held-out voice
turns of the record (env.held_out) and the candidate's own tests, each run for the candidate and the incumbent in
turn. KPIs (voice.reply.KPIS): handoff agreement on the labelled cases, the share of replies fit to speak, the
median time to the first word; and the share of the candidate's own tests it passes. The outcome:
  worse   if it is below the incumbent by more than one case on handoff agreement or spoken form, slower by more
          than 30% plus 150 ms, or passes fewer than three in four of its own tests
  better  if not worse and above the incumbent by more than one case on handoff agreement or spoken form
          (compared as counts, unrounded: exactly one case is never enough)
  same    otherwise (no measurable difference: one run per case, so one case is the margin)
A better candidate is proposed for activation (companion.activate, gate propose): the owner decides.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from environment import Env
from environment.db import database_url
from voice import reply

GATEWAY = os.environ.get("GATEWAY_URL", "http://gateway:8080")
KEY = os.environ.get("JUDGE_KEY", "")
MODEL = os.environ.get("JUDGE_MODEL") or "local/slow"
CASES = Path(os.environ.get("JUDGE_CASES") or "/cases")
NAME = "judge 0.1 (environment/judge.py)"


def log(*a):
    print("judge:", *a, file=sys.stderr, flush=True)


def labelled(name: str) -> list[dict]:
    f = CASES / f"{name}.jsonl"
    return [json.loads(l) for l in f.read_text().splitlines() if l.strip()] if f.exists() else []


def kpis(results: list[dict], labels: list[dict]) -> dict:
    by = {r["utterance"]: r for r in results}
    agree = [(by[c["utterance"]]["handoff"] is not None) == c["expect_handoff"] for c in labels if c["utterance"] in by]
    firsts = [r["first_token_ms"] for r in results if r["first_token_ms"] is not None]
    # unrounded: the outcome compares them, and a rounded rate can push a one-case gap over the margin (verdict 1,
    # 2026-11-18: 29/30 against 28/30 read as 0.967 > 0.933 + 1/30); the verdict's table rounds them for people
    return {"handoff_agreement": sum(agree) / len(agree) if agree else None,
            "spoken_form": sum(r["spoken_ok"] for r in results) / len(results) if results else None,
            "first_token_ms": statistics.median(firsts) if firsts else None}


def outcome(cand: dict, inc: dict, own: float | None, n_labels: int, n_all: int) -> str:
    # the margin is one case, with a little room so that exactly one case never clears it
    tl, ts = 1 / max(n_labels, 1) + 1e-9, 1 / max(n_all, 1) + 1e-9
    worse = (cand["handoff_agreement"] < inc["handoff_agreement"] - tl or cand["spoken_form"] < inc["spoken_form"] - ts
             or cand["first_token_ms"] > inc["first_token_ms"] * 1.3 + 150 or (own is not None and own < 0.75))
    if worse:
        return "worse"
    if cand["handoff_agreement"] > inc["handoff_agreement"] + tl or cand["spoken_form"] > inc["spoken_form"] + ts:
        return "better"
    return "same"


def judge(c, cid: int) -> tuple[int, str]:
    env, name, card, against = c.execute("select env, name, card, against from env.component where id = %s", (cid,)).fetchone()
    inc_card = c.execute("select card from env.component where id = %s", (against,)).fetchone()[0] if against else reply.SEED
    if name != reply.NAME:
        vid = c.execute("select env.record_verdict(%s, 'failed', '{}', '{}', %s, %s)",
                        (cid, Jsonb({"error": f"no cases for component {name}"}), NAME)).fetchone()[0]
        return vid, "failed"
    labels = labelled(name)
    held = [r[0] for r in c.execute(f"select body->>'text' from env.signal where key = '{env}.voice.heard' and env.held_out(id) "
                                    "and coalesce(body->>'text', '') <> '' order by id desc limit 40").fetchall()]
    own = [t for t in card.get("tests") or [] if isinstance(t, dict) and "utterance" in t]
    utterances = list(dict.fromkeys([l["utterance"] for l in labels] + held + [t["utterance"] for t in own]))
    res = {"candidate": [], "incumbent": []}
    t0 = time.time()
    for i, u in enumerate(utterances):
        order = (("candidate", card), ("incumbent", inc_card)) if i % 2 == 0 else (("incumbent", inc_card), ("candidate", card))
        for who, cd in order:
            try:
                res[who].append(reply.run(cd, u, GATEWAY, KEY, MODEL, f"judge-{cid}-{who}-{i}"))
            except Exception as e:                    # noqa: BLE001 - a failed call counts against whoever made it
                res[who].append({"utterance": u, "spoken": "", "handoff": None, "spoken_ok": False, "first_token_ms": None, "error": str(e)})
    kc, ki = kpis(res["candidate"], labels), kpis(res["incumbent"], labels)
    if None in kc.values() or None in ki.values():
        out = "failed"
    else:
        by = {r["utterance"]: r for r in res["candidate"]}
        own_pass = sum((by[t["utterance"]]["handoff"] is not None) == t["expect_handoff"] for t in own) / len(own) if own else None
        out = outcome(kc, ki, own_pass, len(labels), len(utterances))
        kc["own_tests"] = round(own_pass, 3) if own_pass is not None else None
    r3 = lambda v: round(v, 3) if isinstance(v, float) else v  # noqa: E731
    table = {k: {"candidate": r3(kc.get(k)), "incumbent": r3(ki.get(k)), **{x: reply.KPIS[k][x] for x in ("target", "higher_is_better")}}
             for k in reply.KPIS}
    table["own_tests"] = {"candidate": kc.get("own_tests"), "incumbent": None, "target": 0.75, "higher_is_better": True}
    cases = {"labelled": len(labels), "held_out": len(held), "card_tests": len(own), "seconds": round(time.time() - t0)}
    vid = c.execute("select env.record_verdict(%s, %s, %s, %s, %s, %s)",
                    (cid, out, Jsonb(table), Jsonb(cases), Jsonb({"candidate": res["candidate"], "incumbent": res["incumbent"]}), NAME)).fetchone()[0]
    if out == "better":
        version = c.execute("select version from env.component where id = %s", (cid,)).fetchone()[0]
        Env(c).act(f"{env}.activate", {"component": cid, "name": name, "version": version, "verdict": vid,
                                       "kpis": {k: [v["incumbent"], v["candidate"]] for k, v in table.items() if v["incumbent"] is not None},
                                       "why": card.get("rationale")}, NAME)
    return vid, out


def once(c) -> bool:
    cid = c.execute("select env.claim_component()").fetchone()[0]
    if cid is None:
        return False
    log(f"judging component {cid}")
    try:
        vid, out = judge(c, cid)
    except Exception as e:                            # noqa: BLE001 - recorded, so the component is not left being judged
        vid = c.execute("select env.record_verdict(%s, 'failed', '{}', '{}', %s, %s)",
                        (cid, Jsonb({"error": f"{type(e).__name__}: {e}"}), NAME)).fetchone()[0]
        out = "failed"
    log(f"component {cid}: {out} (verdict {vid})")
    return True


def main():
    single = sys.argv[1:] == ["once"]
    while True:
        try:
            with psycopg.connect(database_url(), autocommit=True) as c:
                while True:
                    found = once(c)
                    if single:
                        return
                    if not found:
                        time.sleep(10)
        except psycopg.OperationalError as e:
            log(f"database: {e}; retrying")
            time.sleep(10)


if __name__ == "__main__":
    main()
