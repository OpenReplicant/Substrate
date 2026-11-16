"""The lookups agent's model handler (agent.yaml, `main`): one call to the model a step, through the gateway, with
the episode shown as a log that only grows (`context: append-only`), and the environment's actions offered as
tools in the OpenAI format (which Granite followed in the trial, S-100). The tool it calls is the step's action.

    make(slug, cfg, gateway, package_dir) registers the handler `slug` with the runner (ladder.handler)

`cfg` is the handler's line in agent.yaml with the parameters and the environment's model beside it. Nothing here
imports the store; `gateway` is the handlers plugin's Gateway, built with the caller's key (live) or the one key a
judged run holds.
"""
from __future__ import annotations

import json
import secrets
from pathlib import Path

from ladder import Answer, Escalate, handler

NOTE_CUT = "\n[cut: the log is full]"
RESERVE = 300           # characters the log keeps free for the step that reads it


def text(claims: list[dict]) -> str:
    """Claims as lines the model reads: what each source said, with the time it was read."""
    out, last = [], None
    for c in claims or []:
        if c.get("property") == "question":
            out.append(str(c.get("value")))
            continue
        head = (c.get("source"), c.get("time"))
        if head != last and c.get("source") not in (None, "environment"):
            out.append(f"from {c['source']}" + (f" (read {c['time']})" if c.get("time") else ""))
        last = head
        who = "" if c.get("subject") in (c.get("source"), "environment") else f"{c['subject']} "
        value = c.get("value")
        out.append(f"{who}{c.get('property')}: {value if isinstance(value, str) else json.dumps(value)}")
    return "\n".join(out)


def tools(actions: list[dict]) -> list[dict]:
    return [{"type": "function", "function": {
        "name": a["kind"], "description": a["description"],
        "parameters": {"type": "object", "properties": {k: {"type": "number" if k == "confidence" else "string", "description": d}
                                                        for k, d in a["arguments"].items()},
                       "required": a.get("required") or []}}} for a in actions]


def messages(fixed: str, item: dict, window: int) -> list[dict] | None:
    """The log: the fixed part, the question, then each action and what it returned. Each observation is cut to
    what is left of `window` (the same cut every time it is rendered, so what was sent stays byte for byte the
    same), keeping RESERVE characters free; None when no room is left for another step."""
    steps = item.get("episode") or []
    observations = [s["observation"] for s in steps] + [item.get("observation")]
    log = [{"role": "system", "content": fixed}, {"role": "user", "content": text(observations[0])}]
    used = len(fixed) + len(log[1]["content"])
    for n, s in enumerate(steps, 1):
        a = dict(s.get("action") or {})
        kind = a.pop("kind", None)
        args = json.dumps(a, sort_keys=True, ensure_ascii=False)
        body = text(observations[n])
        left = window - used - len(args) - 40 - RESERVE
        if left < 100:
            return None
        if len(body) > left:
            body = body[:left - len(NOTE_CUT)] + NOTE_CUT
        log.append({"role": "assistant", "content": "", "tool_calls": [{"id": f"call_{n}", "type": "function",
                                                                        "function": {"name": str(kind), "arguments": args}}]})
        log.append({"role": "tool", "tool_call_id": f"call_{n}", "content": body})
        used += len(args) + 40 + len(body)
    return log if window - used >= RESERVE else None


def make(slug: str, cfg: dict, gateway, package_dir: Path):
    package_dir = Path(package_dir)
    instructions = (package_dir / cfg.get("instructions", "handlers/instructions.md")).read_text().strip()
    notes_path = package_dir / cfg.get("notes", "notes/notes.md")
    notes = "\n".join(l for l in notes_path.read_text().splitlines() if l.strip() and not l.startswith("#")) if notes_path.is_file() else ""
    fixed = instructions + (f"\n\nNotes from earlier questions:\n{notes}" if notes else "")
    p = cfg.get("parameters") or {}
    value = lambda k, d: float((p.get(k) or {}).get("value", d)) if isinstance(p.get(k), dict) else float(p.get(k, d))  # noqa: E731
    sure_at, max_steps, window = value("sure_at", 0.8), int(value("max_steps", 6)), int(value("window", 9000))

    @handler(slug)
    def main(item, ask):
        if not gateway.ready():
            return Escalate("no gateway configured (gateway_url, and a key or the secret that derives one)")
        offered = item.get("actions") or []             # the same tools every step, so the prefix the model saw holds
        log = messages(fixed, item, window)
        if log is None:
            return Escalate("the log is full: no room for another step")
        if item.get("step", 1) >= max_steps:            # the last step: said in the new bytes, never in the sent ones
            log[-1] = {**log[-1], "content": log[-1]["content"] + "\n[last step: call answer or hand_off now]"}
        call_id = secrets.token_hex(12)
        meta = {"gateway_call": call_id, "model": cfg["model"]}
        code, r = gateway.chat(f"handler:{slug}", cfg["model"], log, int(cfg.get("max_tokens", 300)), call_id, tools=tools(offered))
        meta["usage"] = r.get("usage")
        if code != 200:
            msg = ((r.get("error") or {}).get("message") if isinstance(r.get("error"), dict) else r.get("error")) or ""
            return Escalate(f"gateway {code}: {str(msg)[:160]}", meta=meta)
        msg = ((r.get("choices") or [{}])[0].get("message")) or {}
        wanted = msg.get("tool_calls") or []
        if not wanted:     # a reply in words, not a tool call: taken as the answer only if it is short
            words = (msg.get("content") or "").strip()
            if words and len(words) <= 200:
                return Answer({"kind": "answer", "value": words}, sure_at, note="answered in words, not with the answer tool", meta=meta)
            return Escalate(f"no tool call in the reply: {words[:120]!r}", meta=meta)
        fn = wanted[0].get("function") or {}           # one action a step: a second tool call in the reply is not taken
        try:
            args = fn.get("arguments")
            args = json.loads(args) if isinstance(args, str) else dict(args or {})
        except (ValueError, TypeError):
            return Escalate(f"tool arguments that are not JSON: {str(fn.get('arguments'))[:120]!r}", meta=meta)
        action = {"kind": fn.get("name"), **{k: v for k, v in args.items() if k != "kind"}}
        if action["kind"] != "answer":
            return Answer(action, 1.0, note="a tool call carries no confidence", meta=meta)
        try:
            conf = float(action.pop("confidence"))
        except (KeyError, TypeError, ValueError):
            conf = sure_at
        conf = min(max(conf, 0.0), 1.0)
        if conf < sure_at:
            return Escalate(f"not sure ({conf} < {sure_at}) of {str(action.get('value'))[:80]!r}", meta=meta)
        return Answer(action, conf, meta=meta)

    return main
