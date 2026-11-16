"""The record pass (docs/tasks/rd-pipeline.md, step 3): each paper's abstract read by a model into the fixed fields of the
reading environment (environment.py), the gate in code deciding what stays.

    order(papers)             the papers to read: testable first, most-listed first, then the rest in the same order
    read(paper, ...)          one paper: one model call through the gateway, the reply through the environment's gate
    fields_of(final)          what to write onto the item for a read paper

Plain functions over dicts, so the tests run them with a fake gateway and no store. The extractor (papers_plugin.py)
writes the result as claims: each field's quote is the cited sentences' text, the author is the model that read it.
"""
from __future__ import annotations

import secrets
import sys
import time
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent
for p in (str(PACKAGE), str(PACKAGE.parents[1] / "plugins/handlers")):
    if p not in sys.path:
        sys.path.insert(0, p)

import environment  # noqa: E402
import reading  # noqa: E402

FIELDS = ("component_kind", "slot", "does", "result", "needs")


def order(papers: list[dict]) -> list[dict]:
    """Papers with an abstract: testable first, then by how many lists name each (most first), then identifier."""
    have = [p for p in papers if (p.get("abstract") or "").strip()]
    return sorted(have, key=lambda p: (p.get("testable") is not True, -(p.get("listing_count") or 0), p.get("arxiv_id") or p["slug"]))


def read(paper: dict, fixed: str, model: str, gateway, caller: str, max_tokens: int = 700, waits=(30, 60, 120), sleep=time.sleep) -> dict:
    """One paper through one model call. Returns {"final": the environment's final state, "usage", "call"} or
    {"error": why, "retry": bool}; a 429 (the gateway's or a free model's limit) waits and tries again, up to three times."""
    env = environment.make()
    case = {"id": paper.get("arxiv_id") or paper["slug"], "arxiv_id": paper.get("arxiv_id"), "title": paper.get("title"),
            "abstract": paper.get("abstract")}
    obs = env.reset(case, 0)
    call = secrets.token_hex(12)
    for wait in (*waits, None):
        code, reply = gateway.chat(caller, model, reading.messages(fixed, obs), max_tokens, call, tools=reading.tools(env.actions()))
        if code != 429 or wait is None:
            break
        sleep(wait)
    if code != 200:
        msg = ((reply.get("error") or {}).get("message") if isinstance(reply.get("error"), dict) else reply.get("error")) or ""
        return {"error": f"gateway {code}: {str(msg)[:160]}", "retry": code in (429, 500, 502, 503, 504, 0), "call": call}
    action, why = reading.action_of(reply)
    if action is None:
        return {"error": why, "retry": False, "call": call, "usage": reply.get("usage")}
    env.step(action)
    return {"final": env.final(), "usage": reply.get("usage"), "call": call}


def fields_of(final: dict) -> tuple[dict, dict]:
    """(the fields to write, the evidence for each): every record field is written, None where the gate left it empty, so
    a read again leaves nothing of an earlier one behind. Evidence is {field: {quote, span}} where sentences were cited."""
    record = final.get("record") or {}
    fields = {f: (record.get(f) or {}).get("value") for f in FIELDS}
    return fields, {f: v for f, v in record.items() if v.get("sentences")}


def spans(abstract: str, cited: dict) -> dict:
    """Evidence for each cited field: the quote is the cited sentences' text, the span says which sentences and where."""
    out = {}
    for f, v in cited.items():
        a, b = environment.span_of(abstract, v["sentences"])
        out[f] = {"quote": v["quote"], "span": {"pointer": "abstract", "sentences": v["sentences"], "start": a, "end": b}}
    return out


def read_batch(papers: list[dict], fixed: str, model: str, gateway, caller: str, max_tokens: int = 700, waits=(30, 60, 120),
               sleep=time.sleep) -> dict:
    """Several papers in one call (reading.py). Returns {"finals": {id: the environment's final state}, "skipped": [ids the
    answer did not cover], "usage", "call"} or {"error", "retry"}. Each record is run through a fresh environment on its own
    paper's abstract, so a sentence number from a neighbour's longer list is refused when this paper lacks it; an id not in the batch is ignored; the first record of an id
    counts."""
    cases = {(p.get("arxiv_id") or p["slug"]): {"id": p.get("arxiv_id") or p["slug"], "arxiv_id": p.get("arxiv_id"),
                                                 "title": p.get("title"), "abstract": p.get("abstract")} for p in papers}
    envs = {i: environment.make() for i in cases}
    obs = [(i, envs[i].reset(c, 0)) for i, c in cases.items()]
    call = secrets.token_hex(12)
    for wait in (*waits, None):
        code, reply = gateway.chat(caller, model, reading.batch_messages(fixed, obs), max_tokens * len(cases), call,
                                   tools=reading.batch_tool(envs[next(iter(cases))].actions()))
        if code != 429 or wait is None:
            break
        sleep(wait)
    if code != 200:
        msg = ((reply.get("error") or {}).get("message") if isinstance(reply.get("error"), dict) else reply.get("error")) or ""
        return {"error": f"gateway {code}: {str(msg)[:160]}", "retry": code in (429, 500, 502, 503, 504, 0), "call": call}
    records, why = reading.records_of(reply)
    if records is None:
        return {"error": why, "retry": False, "call": call, "usage": reply.get("usage")}
    finals, actions = {}, {}
    for rec in records:
        i = str(rec.get("id", "")).strip()
        if i not in cases or i in finals:
            continue
        action = {"kind": "record", **{k: v for k, v in rec.items() if k not in ("id", "kind")}}
        envs[i].step(action)
        finals[i], actions[i] = envs[i].final(), action
    return {"finals": finals, "actions": actions, "skipped": [i for i in cases if i not in finals], "usage": reply.get("usage"), "call": call}
