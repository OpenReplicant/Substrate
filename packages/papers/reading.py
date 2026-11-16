"""How a model is shown a paper and how its reply becomes a `record` action: plain functions, no store and no step loop,
so the model handler (handlers/model.py, in an episode) and the record pass (plugin/papers_plugin.py, over the catalog)
read a paper the same way.

    fixed = instructions(directory)             # the instructions and notes: the fixed part of every call
    messages = messages(fixed, observation)     # the call: that, then the paper
    action, why = action_of(reply)              # a chat reply's `record` or `hand_off`, or (None, the reason)
    digest(fixed, model)                        # which model and prompt read a paper (the record pass keeps it)

With `per_call` above 1 (agent.yaml, parameters) one call shows several abstracts, each under its arXiv id, and the answer
carries one record per id (batch_messages, batch_tool, records_of). The gate is the environment's, applied per paper in
that paper's own abstract: a sentence number the paper does not have (one meant for a neighbour) is refused, an id not in the batch is ignored, and a paper the
answer skipped is unread and is asked again in a later call.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def instructions(directory: Path, cfg: dict | None = None) -> str:
    directory, cfg = Path(directory), cfg or {}
    text = (directory / cfg.get("instructions", "handlers/instructions.md")).read_text().strip()
    notes_path = directory / cfg.get("notes", "notes/notes.md")
    notes = "\n".join(l for l in notes_path.read_text().splitlines() if l.strip() and not l.startswith("#")) if notes_path.is_file() else ""
    return text + (f"\n\nNotes from earlier papers:\n{notes}" if notes else "")


def text(claims: list[dict]) -> str:
    return "\n".join(str(c.get("value")) for c in claims or [])


def messages(fixed: str, observation: list[dict]) -> list[dict]:
    return [{"role": "system", "content": fixed}, {"role": "user", "content": text(observation)}]


def prop(k: str, d: str) -> dict:
    """A tool argument: the sentence numbers a field cites are a list of integers, everything else a string."""
    return {"type": "array", "items": {"type": "integer"}, "description": d} if k.endswith("_sentences") else {"type": "string", "description": d}


def tools(actions: list[dict]) -> list[dict]:
    return [{"type": "function", "function": {
        "name": a["kind"], "description": a["description"],
        "parameters": {"type": "object", "properties": {k: prop(k, d) for k, d in a["arguments"].items()},
                       "required": a.get("required") or []}}} for a in actions]


def action_of(reply: dict) -> tuple[dict | None, str]:
    """The action in a chat reply: its first tool call, or a JSON object in words that has the fields. (None, why) if neither."""
    msg = ((reply.get("choices") or [{}])[0].get("message")) or {}
    wanted = msg.get("tool_calls") or []
    if wanted:
        fn = wanted[0].get("function") or {}
        try:
            args = fn.get("arguments")
            args = json.loads(args) if isinstance(args, str) else dict(args or {})
        except (ValueError, TypeError):
            return None, f"tool arguments that are not JSON: {str(fn.get('arguments'))[:120]!r}"
        return {"kind": fn.get("name"), **{k: v for k, v in args.items() if k != "kind"}}, ""
    words = (msg.get("content") or "").strip()
    dec = json.JSONDecoder()
    for i, ch in enumerate(words):
        if ch == "{":
            try:
                obj, _ = dec.raw_decode(words, i)
            except ValueError:
                continue
            if isinstance(obj, dict) and "component_kind" in obj:
                return {"kind": "record", **{k: v for k, v in obj.items() if k != "kind"}}, ""
    return None, f"no tool call in the reply: {words[:120]!r}"


def digest(fixed: str, model: str) -> str:
    """Which model and which prompt (instructions and notes) read a paper: the first 16 hex of their hash."""
    return hashlib.sha256(json.dumps([model, fixed]).encode()).hexdigest()[:16]


# ---- several papers in one call (agent.yaml: parameters.per_call)

BATCH_NOTE = ("\n\nSeveral papers follow, each under its arXiv id. Call record_batch once, with one record for each paper, "
              "each record carrying that paper's id. Cite sentence numbers from that paper's own list, never another paper's.")


def batch_fixed(fixed: str) -> str:
    return fixed + BATCH_NOTE


def batch_messages(fixed: str, observations: list[tuple[str, list[dict]]]) -> list[dict]:
    """`observations`: [(id, the paper's observation)]. Each paper's text already starts with its arXiv id."""
    body = "\n\n".join(f"=== {i} ===\n{text(o)}" for i, o in observations)
    return [{"role": "system", "content": batch_fixed(fixed)}, {"role": "user", "content": body}]


def batch_tool(actions: list[dict]) -> list[dict]:
    rec = next(a for a in actions if a["kind"] == "record")
    props = {"id": {"type": "string", "description": "the paper's arXiv id, as shown after ==="},
             **{k: prop(k, d) for k, d in rec["arguments"].items()}}
    return [{"type": "function", "function": {
        "name": "record_batch", "description": "One record for each paper shown, each with its id. " + rec["description"],
        "parameters": {"type": "object", "properties": {"records": {"type": "array", "items": {
            "type": "object", "properties": props, "required": ["id", *rec.get("required", [])]}}}, "required": ["records"]}}}]


def records_of(reply: dict) -> tuple[list[dict] | None, str]:
    """The records in a chat reply: the record_batch call's `records`, or a JSON object in words that has them."""
    msg = ((reply.get("choices") or [{}])[0].get("message")) or {}
    objs = []
    for c in msg.get("tool_calls") or []:
        args = (c.get("function") or {}).get("arguments")
        try:
            objs.append(json.loads(args) if isinstance(args, str) else dict(args or {}))
        except (ValueError, TypeError):
            return None, f"tool arguments that are not JSON: {str(args)[:120]!r}"
    words = (msg.get("content") or "")
    dec = json.JSONDecoder()
    for i, ch in enumerate(words):
        if ch in "{[":
            try:
                o, _ = dec.raw_decode(words, i)
            except ValueError:
                continue
            objs.append(o if isinstance(o, dict) else {"records": o})
    for o in objs:
        r = o.get("records") if isinstance(o, dict) else None
        if isinstance(r, list):
            return [x for x in r if isinstance(x, dict)], ""
    return None, f"no records in the reply: {words[:120]!r}"
