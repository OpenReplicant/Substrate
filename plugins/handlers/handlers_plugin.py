"""Workbench's handlers plugin (README.md): streams, handlers ranked by measured cost, and the record of every call.

handlers:declare  a YAML file of streams and their handlers, written as items
handlers:run      every stream's inputs up its route; each call recorded, scored against outcomes; handlers re-ranked
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import os
import re
import secrets
import urllib.error
import urllib.request
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


# ---- model handlers (README.md, "Model handlers"): a model behind a gateway that counts every call

def caller_key(secret: str, caller: str) -> str:
    """The gateway key a caller gets, derived from one shared secret so it need not be stored: the gateway's
    config is rendered with the same formula."""
    return "sk-bf-" + hmac.new(secret.encode(), caller.encode(), hashlib.sha256).hexdigest()[:40]


class Gateway:
    """An OpenAI-style chat endpoint that keeps its own record of each call (the gateway), and a read-only
    connection to that record (the meter). The caller's key says whose call it is; a call id sent in a header
    joins the call to the gateway's row."""

    def __init__(self, url: str | None, secret: str | None, meter_url: str | None, key: str | None = None):
        """`secret` derives each caller's key; `key`, given instead, is the one key every call uses (a judged run
        holds only the key its meter gave it, never the secret that would derive anyone's)."""
        self.url, self.secret, self.meter_url, self.key = (url or "").rstrip("/"), secret, meter_url, key

    def ready(self) -> bool:
        return bool(self.url and (self.key or self.secret))

    def chat(self, caller: str, model: str, messages: list, max_tokens: int, call_id: str) -> tuple[int, dict]:
        body = json.dumps({"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0}).encode()
        req = urllib.request.Request(f"{self.url}/v1/chat/completions", body, {
            "Content-Type": "application/json", "x-bf-vk": self.key or caller_key(self.secret, caller), "x-wb-call": call_id})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read() or b"{}")
            except ValueError:
                return e.code, {}

    def records(self, call_ids: list[str]) -> dict[str, dict]:
        """The gateway's own rows for these call ids: model, status, latency (ms), cost (USD), tokens, key."""
        if not self.meter_url or not call_ids:
            return {}
        import psycopg
        with psycopg.connect(self.meter_url, connect_timeout=5) as c:
            rows = c.execute("""select metadata::jsonb->>'x-wb-call', model, status, latency, cost, prompt_tokens, completion_tokens,
                                       virtual_key_name
                                  from logs where metadata::jsonb->>'x-wb-call' = any(%s) and status <> 'processing'""",
                             (call_ids,)).fetchall()
        return {r[0]: {"model": r[1], "status": r[2], "ms": float(r[3] or 0), "usd": float(r[4] or 0), "tokens_in": r[5],
                       "tokens_out": r[6], "caller": r[7]} for r in rows}


def parse_json(text: str):
    """The first JSON object in a model's answer that has an "answer" (it may wrap it in a code fence, a sentence,
    or write more after it)."""
    dec, text, first = json.JSONDecoder(), text or "", None
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _ = dec.raw_decode(text, i)
        except ValueError:
            continue
        if isinstance(obj, dict):
            if "answer" in obj:
                return obj
            first = first or obj
    if first is None:   # almost JSON (a reason left unquoted, say): the answer and confidence by pattern
        a = re.search(r'"answer"\s*:\s*"([^"]+)"', text)
        c = re.search(r'"confidence"\s*:\s*([0-9]*\.?[0-9]+)', text)
        r = re.search(r'"reason"\s*:\s*"?([^"}]*)', text)
        if a and c:
            return {"answer": a.group(1), "confidence": float(c.group(1)), "reason": (r.group(1).strip() if r else None), "lenient": True}
    return first


# how many of the earlier decisions a model handler is shown with each input (the most recent ones)
HISTORY = 20


def model_handler(slug: str, cfg: dict, about: str, gateway: Gateway):
    """Register `slug` as a model handler: it asks its model, through the gateway, for one of `answers` with a
    confidence, and escalates below `sure_at`, on an answer it cannot read, or when the gateway refuses."""
    answers = cfg.get("answers") or []
    sure_at = float(cfg.get("sure_at", 0.8))

    @handler(slug)
    def ask_model(item, ask):
        if not gateway.ready():
            return Escalate("no gateway configured (gateway_url, gateway_secret)")
        call_id = secrets.token_hex(12)
        meta = {"gateway_call": call_id, "model": cfg["model"]}
        shown = {k: item.get(k) for k in ("key", "payload")}
        shown["earlier decisions"] = (item.get("history") or [])[-HISTORY:] if HISTORY else []
        system = (f"You handle one input of this stream: {about}\n"
                  f"Reply with one JSON object and nothing else: {{\"answer\": one of {json.dumps(answers)}, "
                  f"\"confidence\": a number from 0 to 1, \"reason\": one short sentence}}. "
                  "If you cannot tell, say so with a low confidence.")
        code, r = gateway.chat(f"handler:{slug}", cfg["model"], [{"role": "system", "content": system},
                               {"role": "user", "content": json.dumps(shown, default=str)}], int(cfg.get("max_tokens", 400)), call_id)
        if code != 200:
            msg = ((r.get("error") or {}).get("message") if isinstance(r.get("error"), dict) else r.get("error")) or ""
            return Escalate(f"gateway {code}: {str(msg)[:160]}", meta=meta)
        text = ((r.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        got = parse_json(text)
        if not isinstance(got, dict) or got.get("answer") not in answers:
            return Escalate(f"no answer among {answers} in the reply: {text[:120]!r}", meta=meta)
        try:
            conf = float(got.get("confidence"))
        except (TypeError, ValueError):
            return Escalate(f"no confidence in the reply: {text[:120]!r}", meta=meta)
        if not 0 <= conf <= 1:
            return Escalate(f"confidence {conf} is outside [0, 1]", meta=meta)
        if conf < sure_at:
            return Escalate(f"not sure ({conf} < {sure_at}): {str(got.get('reason') or '')[:160]}", meta=meta)
        return Answer(got["answer"], conf, note=str(got.get("reason") or "")[:300] or None, meta=meta)

    return ask_model


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
                config = {k: v for k, v in h.items() if k not in ("kind", "entry", "description", "component", "title")}
                hid = ctx.upsert("handler", hslug, {"stream": sslug, "kind": h["kind"], "entry": h.get("entry") or hslug,
                                                    "description": h.get("description"), "component": h.get("component"),
                                                    **({"config": config} if config else {})},
                                 title=h.get("title") or hslug, source=src)
                ctx.relate("handler", hid, "subscribesTo", "stream", sid, source=src)
        ctx.done("stream")
        ctx.done("handler")

    def run(ctx, inputs):
        q = ctx.conn.execute
        streams = q("select id, slug, source, answers from api.stream where wb.live(id) order by slug").fetchall()
        hs = {r[1]: {"id": str(r[0]), "slug": r[1], "stream": r[2], "kind": r[3], "entry": r[4], "cost": r[5], "measured": r[6], "title": r[7],
                     "config": r[8] or {}}
              for r in q("select id, slug, stream, kind, entry, cost, measured, title, config from api.handler where wb.live(id)").fetchall()}
        gateway = Gateway(wb.setting("gateway_url"), wb.setting("gateway_secret"), wb.setting("meter_url"))
        about = {r[0]: r[1] or r[0] for r in q("select slug, description from api.stream where wb.live(id)").fetchall()}
        for h in hs.values():                     # a model handler is the built-in `model`, with its own settings
            if h["kind"] == "model" and h["entry"] == "model" and h["config"].get("model"):
                model_handler(h["slug"], h["config"], about.get(h["stream"], h["stream"]), gateway)
                h["entry"] = h["slug"]
        models = {h["slug"] for h in hs.values() if h["kind"] == "model"}
        cost_of = lambda h: h["cost"] if h["measured"] and h["cost"] else PRIOR[h["kind"]]  # noqa: E731
        totals = Counter()
        for sid, sslug, source, answers in streams:
            mine = sorted((h for h in hs.values() if h["stream"] == sslug), key=lambda h: rank_key(cost_of(h)))
            order = [h["slug"] for h in mine]
            entries = {h["slug"]: h["entry"] for h in mine}
            people = {h["slug"] for h in mine if h["kind"] == "person"}
            existing = {}
            for cslug, iname, hname, kind, reason in q("select slug, input, handler, kind, reason from api.call where stream = %s and wb.live(id)",
                                                       (sslug,)).fetchall():
                # a model call the gateway turned away (a provider's limit, an outage) is not the model's judgment:
                # it is made again, like a person's call still waiting
                retry = kind == "waiting" or (hname in models and kind == "escalate" and (reason or "").startswith("gateway "))
                existing.setdefault(iname, {})[hname] = (cslug, "waiting" if retry else kind)
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
                    # a handler that joined the stream later is asked too, where its answer can still count: on an
                    # advisory stream, or an input still open
                    late = [h for h in order if h not in seen and h not in people]
                    if late and ((answers or "final") == "advisory" or not o):
                        calls += Runner(late, entries, "advisory", reveal=people).handle(strip(item))
                        totals["late"] += len(late)
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
                    if c.handler in models:
                        at = utc(dt.datetime.now(dt.timezone.utc))
                        if c.kind in ("answer", "escalate") and not (c.meta or {}).get("gateway_call") and "no gateway configured" not in (c.reason or ""):
                            c.kind, c.reason = "refused", "a model handler's call must go through the gateway (it sent no call id)"
                        cost = {"person": 0, "usd": 0, "seconds": round(c.seconds, 4)}   # until the gateway's record is read
                    fields = {"stream": sslug, "input": islug, "handler": c.handler, "kind": c.kind,
                              "value": None if c.value is None else c.value if isinstance(c.value, str) else json.dumps(c.value),
                              "confidence": c.confidence, "reason": c.reason or c.note, "escalate_to": c.to, "cost": cost, "at": at,
                              "parent": slugs.get(calls[c.parent].handler) if c.parent is not None else None,
                              **({"meta": c.meta} if c.meta else {}), **({"metered": False} if c.handler in models else {})}
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
        meter(ctx, gateway, totals, grace_minutes=float(wb.setting("meter_grace_minutes") or 15))
        rank(ctx, hs)
        ctx.log(f"{len(streams)} streams; {totals['new']} new inputs, {totals['late']} late handler calls, {totals['calls']} calls made or recorded; "
                f"{totals['metered']} model calls metered by the gateway, {totals['unmetered']} not yet, {totals['unseen']} refused unseen; "
                f"{len(hs)} handlers ranked")

    def meter(ctx, gateway, totals, wait: float = 20.0, grace_minutes: float = 15.0):
        """A model call's cost is the gateway's record of it, never the handler's: its money and time, its tokens.
        A call the gateway still has no record of after the grace period is refused (it went around the gateway,
        or never reached it)."""
        import time
        q = ctx.conn.execute
        todo = q("""select slug, meta->>'gateway_call', at, title, handler from api.call
                     where wb.live(id) and metered is false and meta ? 'gateway_call'""").fetchall()
        if not todo:
            return
        ids = [r[1] for r in todo]
        found, t0 = {}, time.time()
        while True:          # the gateway writes its log in batches
            try:
                found = gateway.records(ids)
            except Exception as e:  # noqa: BLE001 - an unreachable meter leaves calls unmetered, not wrong
                ctx.log(f"meter: {type(e).__name__}: {str(e)[:160]}")
                break
            if len(found) == len(ids) or time.time() - t0 > wait:
                break
            time.sleep(2)
        now = dt.datetime.now(dt.timezone.utc)
        for cslug, cid, at, title, hname in todo:
            rec = found.get(cid)
            if rec and rec.get("caller") not in (None, f"handler:{hname}"):
                ctx.upsert("call", cslug, {"metered": True, "kind": "refused",
                                           "reason": f"the gateway records this call under {rec['caller']}, not handler:{hname}"}, title=title)
                totals["unseen"] += 1
            elif rec:
                ctx.upsert("call", cslug, {"metered": True, "cost": {"person": 0, "usd": round(rec["usd"], 6), "seconds": round(rec["ms"] / 1000, 3),
                                                                     "tokens_in": rec["tokens_in"], "tokens_out": rec["tokens_out"]}}, title=title)
                totals["metered"] += 1
            elif at and now - dt.datetime.fromisoformat(at) > dt.timedelta(minutes=grace_minutes):
                ctx.upsert("call", cslug, {"metered": True, "kind": "refused",
                                           "reason": "the gateway has no record of this call"}, title=title)
                totals["unseen"] += 1
            else:
                totals["unmetered"] += 1

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
