"""An author of components (S-151): reads the training slice of the record and the active card, and submits a new
version for the judge. It never sees what the judge holds out (env.training_turns leaves it out; the labelled
cases are in the judge's container only).

    python3 -m environment.author voice_reply [WHY]     # in the companion's container; or the `improve` actuator

The first author writes the voice head's reply component with the local model (AUTHOR_MODEL, local/gemma by
default, thinking off unless AUTHOR_REASONING says otherwise), so what the owner said aloud stays on this machine (P3).
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request

import psycopg
from psycopg.types.json import Jsonb

from store.mcp import database_url

ENV = "companion"
GATEWAY = os.environ.get("GATEWAY_URL", "http://gateway:8080")
MODEL = os.environ.get("AUTHOR_MODEL") or "local/gemma"
KEY = os.environ.get("COMPANION_AUTHOR_KEY", "")

BRIEF = """You improve one component of a voice assistant: the instructions and settings its local model uses to
answer what the owner says aloud. Its replies are spoken by text-to-speech. When the owner asks for real work
(anything needing tools, files, the web, their machine, a schedule or a long answer) the reply must end with one
line "HANDOFF: <the request>", which goes to a separate assistant with tools; small talk and quick facts it answers
itself, with no HANDOFF line.

A judge you cannot see will test your version against the current one on cases you are not shown, measuring:
{kpis}
It is adopted only if it is better on these and the owner agrees.

The current card:
{card}

What happened recently (utterance heard -> what was said back, with timings; "interrupted" means the owner spoke
over it; "handoff" means it handed the request over):
{turns}

{why}

Write the next version. Change only what the record or the measures give you reason to change, and say why.
Answer with one JSON object and nothing else:
{{"intent": "...", "params": {{"system": "<the full instructions>", "temperature": <0..1.5>, "max_tokens": <32..1000>,
  "reasoning_effort": "none", "history_turns": <0..40>}},
 "tests": [{{"utterance": "...", "expect_handoff": true|false}}, ...at least four, both kinds],
 "rationale": "<what you changed and the evidence for it, in two or three sentences>"}}"""


def turns_text(rows) -> str:
    if not rows:
        return "(no voice turns recorded yet)"
    out = []
    for heard_id, heard, at, said, comp, stt, first, turn, interrupted, handed in rows[:60]:
        flags = ", ".join(f for f, on in (("interrupted", interrupted), ("handoff", handed)) if on)
        out.append(f"- [{heard_id}] \"{heard}\" -> \"{said or '(nothing)'}\" (first audio {first} ms, turn {turn} ms{', ' + flags if flags else ''})")
    return "\n".join(out)


def ask(prompt: str) -> str:
    """The model's answer, streamed: with thinking on it writes for minutes (about 15 tokens a second here), past the
    gateway's 300 s limit on one request; a stream is only cut when it goes quiet."""
    body = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.4,
                       "max_tokens": 8000, "stream": True,
                       # thinking off by default: with it (medium) Gemma 4 thought for 460 s, filled 8000 tokens and
                       # never answered; without, a whole card in 34 s (2026-11-18)
                       "reasoning_effort": os.environ.get("AUTHOR_REASONING") or "none"}).encode()
    req = urllib.request.Request(f"{GATEWAY}/v1/chat/completions", body, {"Content-Type": "application/json", "x-bf-vk": KEY})
    out = []
    with urllib.request.urlopen(req, timeout=1800) as r:
        for line in r:
            line = line.decode("utf-8", "replace").strip()
            if not line.startswith("data:") or line[5:].strip() == "[DONE]":
                continue
            try:
                delta = json.loads(line[5:])["choices"][0].get("delta") or {}
            except (ValueError, KeyError, IndexError):
                continue
            out.append(delta.get("content") or "")
    return "".join(out)


def parse(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("the author's answer has no JSON object")
    card = json.loads(m.group(0))
    p = card.get("params") or {}
    if not isinstance(p.get("system"), str) or len(p["system"]) < 100:
        raise ValueError("the author's card has no instructions")
    tests = [t for t in card.get("tests") or [] if isinstance(t, dict) and isinstance(t.get("utterance"), str)
             and isinstance(t.get("expect_handoff"), bool)]
    return {"intent": str(card.get("intent") or ""), "params": p, "tests": tests, "rationale": str(card.get("rationale") or "")}


def improve(name: str, why: str | None, author: str) -> int:
    from voice import reply
    if name != reply.NAME:
        raise ValueError(f"no author for component {name}")
    with psycopg.connect(database_url(), autocommit=True) as c:
        row = c.execute("select id, card from env.active_component(%s, %s)", (ENV, name)).fetchone()
        current = row[1] if row else reply.SEED
        rows = c.execute("select * from env.training_turns(%s, 200)", (ENV,)).fetchall()
        kpis = "\n".join(f"- {k}: {v['how']} (target {v['target']})" for k, v in reply.KPIS.items())
        shown = {k: current.get(k) for k in ("intent", "params", "tests", "rationale")}
        prompt = BRIEF.format(kpis=kpis, card=json.dumps(shown, indent=1), turns=turns_text(rows),
                              why=f"The owner's reason for asking: {why}" if why else "")
        new = parse(ask(prompt))
        card = {**reply.SEED, **{k: v for k, v in current.items() if k in ("trigger", "action", "kpis")}, **new,
                "params": {**reply.SEED["params"], **new["params"]}, "kpis": reply.KPIS,
                "source_cases": [r[0] for r in rows[:60]]}
        return c.execute("select env.submit_component(%s, %s, %s, %s)", (ENV, name, Jsonb(card), f"{author} with {MODEL}")).fetchone()[0]


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cid = improve(sys.argv[1], " ".join(sys.argv[2:]) or None, "author")
    print(f"submitted component {cid}")


if __name__ == "__main__":
    main()
