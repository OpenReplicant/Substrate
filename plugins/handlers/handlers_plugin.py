"""Workbench's handlers plugin (README.md): streams, handlers ranked by measured cost, and the record of every call.

handlers:declare  a YAML file of streams and their handlers, written as items
handlers:run      every stream's inputs up its route; each call recorded, scored against outcomes; handlers re-ranked
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from collections import Counter
from pathlib import Path

import yaml

import ladder
from ladder import KINDS, PRIOR, Answer, Dropped, Escalate, Runner, Waiting, handler, rank_key


def utc(t) -> str | None:
    if t is None:
        return None
    if isinstance(t, (int, float)):
        t = dt.datetime.fromtimestamp(t, dt.timezone.utc)
    return t.astimezone(dt.timezone.utc).isoformat(timespec="seconds")


def slug(text: str) -> str:
    t = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return t if len(t) <= 160 else t[:150] + "-" + t[-9:]


# ---- built-in handlers (README.md, "Built-in handlers")

@handler("precedent")
def precedent(item, ask):
    """What a person decided before on decisions like this one (same key, less its last part). Only history from
    before the input arrived is in `item`, so a replay cannot see its own future."""
    key = item.get("key") or ""
    pattern = key.rsplit(":", 1)[0]
    same = [h["value"] for h in item.get("history") or [] if h["key"].rsplit(":", 1)[0] == pattern]
    if not same:
        return Escalate(f"no earlier decision on {pattern}:*")
    top, n = Counter(same).most_common(1)[0]
    return Answer(top, round(n / (len(same) + 1), 3), note=f"{n} of {len(same)} earlier decisions on {pattern}:* were {top}")


@handler("review-lane")
def review_lane(item, ask):
    """The review lane: the person's decision is the answer."""
    o = item.get("outcome")
    if not o:
        return Waiting("open in the review lane")
    if o["value"] == "withdrawn":
        return Dropped(f"withdrawn by {o['by']}")
    return Answer(o["value"], 1.0, note=o.get("note"))


# ---- sources (README.md, "Sources"): each yields inputs as dicts

def from_decisions(conn, source: dict, root: Path):
    """Each decision `raised_by` raised, oldest first. History is what people decided before it arrived."""
    rows = conn.execute("""select id, key, kind, raised_by, subject, status, decided_by, decided_at, note, created_at
                             from wb.decision where raised_by = %s and kind = %s order by created_at, id""",
                        (source["raised_by"], source.get("decision_kind", "gap"))).fetchall()
    people = [r for r in rows if r[5] in ("approved", "declined") and r[6] and r[6] != r[3]]
    for did, key, kind, raised_by, subject, status, decided_by, decided_at, note, created_at in rows:
        if status in ("approved", "declined") and decided_by and decided_by != raised_by:
            outcome = {"value": status, "by": decided_by, "at": utc(decided_at), "note": note}
        elif status == "withdrawn":
            outcome = {"value": "withdrawn", "by": decided_by or raised_by, "at": utc(decided_at)}
        else:
            outcome = None
        yield {
            "id": f"{key or did}-{str(did)[:8]}",      # a key can be raised again after it closed: the decision is the input
            "key": key or str(did), "payload": {"decision": str(did), "kind": kind, "subject": subject},
            "arrived_at": created_at, "outcome": outcome,
            "history": [{"key": p[1], "value": p[5], "at": utc(p[7])} for p in people if p[7] < created_at],
        }


def from_jsonl(conn, source: dict, root: Path):
    """Calls already made outside the runner, one JSON line each (a hook that records its own runs)."""
    path = root / source["path"]
    if not path.is_file():
        return
    for n, line in enumerate(path.read_text().splitlines(), 1):
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("stream") != source["stream"]:
            continue
        started = float(r.get("started") or 0)
        ok = int(r.get("exit", 1)) == 0
        call = (ladder.Call(r["handler"], "answer", value="ok", confidence=1.0, seconds=float(r.get("seconds") or 0), note=r.get("note"))
                if ok else
                ladder.Call(r["handler"], "escalate", reason=f"exit {r.get('exit')}" + (f": {r['note']}" if r.get("note") else ""),
                            seconds=float(r.get("seconds") or 0)))
        yield {"id": f"{r['handler']}-{started:.3f}", "key": f"{r['handler']}-{started:.3f}", "payload": {"input": r.get("input"), "line": n},
               "arrived_at": dt.datetime.fromtimestamp(started, dt.timezone.utc), "outcome": None, "calls": [call]}


SOURCES = {"decisions": from_decisions, "jsonl": from_jsonl}


def register(wb):
    root = Path(wb.setting("root") or os.getcwd())

    def declare(ctx, inputs):
        path = Path(inputs["file"])
        path = path if path.is_absolute() else root / path
        data = path.read_bytes()
        src = ctx.source(f"file:{inputs.get('uri') or path.name}", data, "application/yaml")
        spec = yaml.safe_load(data) or {}
        for sslug, s in (spec.get("streams") or {}).items():
            src_kind = (s.get("source") or {}).get("kind")
            if src_kind not in SOURCES:
                raise ValueError(f"stream {sslug}: source kind {src_kind!r} is not one of {sorted(SOURCES)}")
            sid = ctx.upsert("stream", sslug, {"description": s.get("description"), "source": s.get("source"),
                                                "answers": s.get("answers", "final"), "outcome": s.get("outcome")},
                             title=s.get("title") or sslug, source=src)
            for hslug, h in (s.get("handlers") or {}).items():
                if h.get("kind") not in KINDS:
                    raise ValueError(f"handler {hslug}: kind {h.get('kind')!r} is not one of {KINDS}")
                hid = ctx.upsert("handler", hslug, {"stream": sslug, "kind": h["kind"], "entry": h.get("entry") or hslug,
                                                    "description": h.get("description"), "component": h.get("component")},
                                 title=h.get("title") or hslug, source=src)
                ctx.relate("handler", hid, "subscribesTo", "stream", sid, source=src)
        ctx.done("stream")
        ctx.done("handler")

    def run(ctx, inputs):
        q = ctx.conn.execute
        streams = q("select id, slug, source, answers from api.stream where wb.live(id) order by slug").fetchall()
        hs = {r[1]: {"id": str(r[0]), "slug": r[1], "stream": r[2], "kind": r[3], "entry": r[4], "cost": r[5], "measured": r[6], "title": r[7]}
              for r in q("select id, slug, stream, kind, entry, cost, measured, title from api.handler where wb.live(id)").fetchall()}
        cost_of = lambda h: h["cost"] if h["measured"] and h["cost"] else PRIOR[h["kind"]]  # noqa: E731
        totals = Counter()
        for sid, sslug, source, answers in streams:
            mine = sorted((h for h in hs.values() if h["stream"] == sslug), key=lambda h: rank_key(cost_of(h)))
            order = [h["slug"] for h in mine]
            entries = {h["slug"]: h["entry"] for h in mine}
            people = {h["slug"] for h in mine if h["kind"] == "person"}
            existing = {}
            for cslug, iname, hname, kind in q("select slug, input, handler, kind from api.call where stream = %s and wb.live(id)", (sslug,)).fetchall():
                existing.setdefault(iname, {})[hname] = (cslug, kind)
            for item in SOURCES[source["kind"]](ctx.conn, {**source, "stream": sslug}, root):
                islug = slug(f"{sslug}-{item['id']}")
                o = item.get("outcome")
                seen = existing.get(islug, {})
                if "calls" in item:                       # made outside the runner: record as given
                    calls = item["calls"]
                elif not seen:                            # new: up the whole route
                    calls = Runner(order, entries, answers or "final", reveal=people).handle(strip(item))
                    totals["new"] += 1
                else:                                     # seen: only calls still waiting are made again
                    calls = []
                    for h, (_, kind) in seen.items():
                        if kind == "waiting":
                            calls += Runner([h], entries, "final", reveal=people).handle(strip(item))
                status = ("dropped" if o and o["value"] == "withdrawn" else "resolved" if o else
                          "resolved" if any(c.kind == "answer" for c in calls) and (answers or "final") == "final" else "open")
                resolved_by = (next((c.handler for c in calls if c.kind == "answer" and c.handler in people), None) if o and o["value"] != "withdrawn"
                               else next((c.handler for c in calls if c.kind == "answer"), None) if status == "resolved" else None)
                iid = ctx.upsert("input", islug, {"stream": sslug, "key": item["key"], "payload": item["payload"],
                                                  "arrived_at": utc(item["arrived_at"]), "status": status, "outcome": o,
                                                  **({"resolved_by": resolved_by} if resolved_by else {})},
                                 title=f"{sslug}: {item['key']}")
                ctx.relate("input", iid, "on", "stream", str(sid))
                slugs = {}
                for n, c in enumerate(calls):
                    cslug = slug(f"{islug}--{c.handler}") + (f"-{n}" if c.handler in slugs else "")
                    slugs[c.handler] = cslug
                    cost = {"person": 0, "usd": 0, "seconds": round(c.seconds, 4)}
                    if c.handler in people and c.kind == "answer" and o and o.get("at"):
                        waited = dt.datetime.fromisoformat(o["at"]) - dt.datetime.fromisoformat(utc(item["arrived_at"]))   # both to the second
                        cost = {"person": 1, "usd": 0, "seconds": round(max(waited.total_seconds(), 0), 0)}
                    elif c.handler in people:
                        cost = {"person": 0, "usd": 0, "seconds": 0}
                    at = utc(dt.datetime.fromisoformat(o["at"])) if c.handler in people and o and o.get("at") else utc(item["arrived_at"])
                    fields = {"stream": sslug, "input": islug, "handler": c.handler, "kind": c.kind,
                              "value": None if c.value is None else c.value if isinstance(c.value, str) else json.dumps(c.value),
                              "confidence": c.confidence, "reason": c.reason or c.note, "escalate_to": c.to, "cost": cost, "at": at,
                              "parent": slugs.get(calls[c.parent].handler) if c.parent is not None else None}
                    with ctx.as_author(f"handler:{c.handler}"):
                        ctx.upsert("call", cslug, fields, title=f"{c.handler} on {item['key']}")
                    totals["calls"] += 1
                # scoring is the run's, not the handler's: an answer against the outcome, once a person has given one
                for hname, (cslug, _) in {**seen, **{c.handler: (slugs[c.handler], c.kind) for c in calls}}.items():
                    row = q("select id, kind, value, title from api.call where slug = %s and wb.live(id)", (cslug,)).fetchone()
                    if not row:
                        continue
                    scorable = o and o["value"] in ("approved", "declined") and row[1] == "answer" and hname not in people
                    ctx.upsert("call", cslug, {"correct": (row[2] == o["value"]) if scorable else None}, title=row[3])
                    ctx.relate("call", str(row[0]), "handles", "input", iid)
                    if hname in hs:
                        ctx.relate("call", str(row[0]), "handledBy", "handler", hs[hname]["id"])
        rank(ctx, hs)
        ctx.log(f"{len(streams)} streams; {totals['new']} new inputs, {totals['calls']} calls made or recorded; {len(hs)} handlers ranked")

    def rank(ctx, hs):
        """Each handler's mean cost over the calls that spent something, its counts, and its rank among all handlers."""
        q = ctx.conn.execute
        stats = {}
        for h in hs.values():
            rows = q("select kind, cost, correct from api.call where handler = %s and wb.live(id)", (h["slug"],)).fetchall()
            spent = [r[1] for r in rows if r[0] in ("answer", "escalate", "refused") and r[1]]
            mean = {k: round(sum(c.get(k, 0) for c in spent) / len(spent), 4) for k in ("person", "usd", "seconds")} if spent else None
            stats[h["slug"]] = {"cost": mean, "measured": bool(spent), "calls": len(rows),
                                "answers": sum(r[0] == "answer" for r in rows), "escalations": sum(r[0] == "escalate" for r in rows),
                                "refusals": sum(r[0] == "refused" for r in rows), "scored": sum(r[2] is not None for r in rows),
                                "correct": sum(r[2] is True for r in rows)}
        ordered = sorted(hs.values(), key=lambda h: (rank_key(stats[h["slug"]]["cost"] or PRIOR[h["kind"]]), h["slug"]))
        for n, h in enumerate(ordered, 1):
            s = stats[h["slug"]]
            ctx.upsert("handler", h["slug"], {**s, "cost": s["cost"] or PRIOR[h["kind"]], "rank": n}, title=h["title"])
        for sid, sslug, answers in q("select id, slug, answers from api.stream where wb.live(id)").fetchall():
            ladder_ = [h["slug"] for h in ordered if h["stream"] == sslug]
            rid = ctx.upsert("route", sslug, {"stream": sslug, "ladder": ladder_, "answers": answers or "final",
                                              "basis": "rank: mean measured cost per call (a person's attention, then money, then seconds); "
                                                       "an unmeasured handler takes its kind's prior"}, title=f"route: {sslug}")
            ctx.relate("route", rid, "orders", "stream", str(sid))

    wb.extractor("declare", declare, "a YAML file of streams and their handlers (--input file=PATH), written as items",
                 {"file": "the streams file"})
    wb.extractor("run", run, "every stream's inputs up its route: each call recorded as the handler's claim, scored "
                             "against outcomes; handlers re-ranked by measured cost")


def strip(item: dict) -> dict:
    """The input as handlers get it; the runner hides `outcome` from all but a person's handler."""
    return {k: v for k, v in item.items() if k != "calls"}
