"""The voice head's reply component (S-151): what the local model is told and how it is called, as a card.

One module for the voice head (which speaks with the active version) and the judge (which runs a candidate and the
incumbent on the same cases), so both run exactly the same thing. Standard library only.

A card (env.component.card) holds: intent, trigger, action, params {system, temperature, max_tokens,
reasoning_effort, history_turns}, kpis (targets), tests [{utterance, expect_handoff}], source_cases, rationale.
"""
from __future__ import annotations

import http.client
import json
import re
import time
import urllib.error
import urllib.request

NAME = "voice_reply"
SYSTEM = """You are the owner's companion, speaking with them out loud. Your words are turned into speech, so:
answer in one to three short spoken sentences; no lists, headings, markdown, emoji or code; say numbers the way a
person says them. Be warm, plain and direct, like a capable friend.

You cannot look things up, run anything, read files or remember beyond this conversation. A separate companion
(Claude, with tools, working in the background) can. When the owner asks for real work (finding something out,
anything with files, the web, their machine, a plan, a long answer), say briefly that you are handing it over, then
end your reply with one line of its own: HANDOFF: <the request, complete and self-contained>. Its answer will be
read out when it comes. Do not hand over small talk or what you can answer yourself.

What you hear is a speech-to-text transcript and may have small mistakes; if it makes no sense, ask once."""
KPIS = {
    "handoff_agreement": {"higher_is_better": True, "target": 0.9,
                          "how": "share of labelled utterances where the reply hands over exactly when it should"},
    "spoken_form": {"higher_is_better": True, "target": 0.9,
                    "how": "share of replies fit to be spoken: no markdown, lists, emoji or code; at most 3 sentences and 60 words"},
    "first_token_ms": {"higher_is_better": False, "target": 800,
                       "how": "median milliseconds from the request to the first word of the reply"},
}
SEED = {
    "intent": "Answer what the owner says aloud in a few spoken sentences, and hand real work to the companion.",
    "trigger": "companion.voice.heard: each utterance the voice head transcribes",
    "action": "speak the reply (Kokoro); a closing HANDOFF line goes to the companion as companion.owner.message",
    "params": {"system": SYSTEM, "temperature": 0.7, "max_tokens": 400, "reasoning_effort": "none", "history_turns": 20},
    "kpis": KPIS,
    "tests": [{"utterance": "Hello, how are you?", "expect_handoff": False},
              {"utterance": "Please find out how much free disk space my computer has.", "expect_handoff": True}],
    "source_cases": [],
    "rationale": "The first version, written by hand (S-149); the seed the judge compares candidates against.",
}


def params(card: dict) -> dict:
    p = {**SEED["params"], **(card.get("params") or {})}
    p["history_turns"] = max(0, min(int(p["history_turns"]), 40))
    p["max_tokens"] = max(32, min(int(p["max_tokens"]), 1000))
    p["temperature"] = max(0.0, min(float(p["temperature"]), 1.5))
    return p


def stream(card: dict, history: list[dict], utterance: str, gateway: str, key: str, model: str, call_id: str = "",
           stop=None):
    """The reply, token by token, from the local model through the gateway. A connection the model's server had
    already closed (the gateway's 502, "closed connection before returning the first response byte", 2026-11-18)
    is tried once more, if nothing has arrived yet. `stop` (a threading.Event) ends it early: closing the
    connection makes llama.cpp stop generating, so an interrupted reply does not go on using the model."""
    for attempt in (1, 2):
        got = False
        try:
            for tok in _stream(card, history, utterance, gateway, key, model, call_id, stop):
                got = True
                yield tok
            return
        except (urllib.error.HTTPError, urllib.error.URLError, ConnectionError, http.client.HTTPException) as e:
            retry = attempt == 1 and not got and (not isinstance(e, urllib.error.HTTPError) or e.code in (502, 503))
            if not retry:
                raise


def _stream(card, history, utterance, gateway, key, model, call_id, stop):
    p = params(card)
    msgs = [{"role": "system", "content": p["system"]}] + (history[-p["history_turns"]:] if p["history_turns"] else []) \
        + [{"role": "user", "content": utterance}]
    body = json.dumps({"model": model, "messages": msgs, "stream": True, "temperature": p["temperature"],
                       "max_tokens": p["max_tokens"], "reasoning_effort": p["reasoning_effort"]}).encode()
    req = urllib.request.Request(f"{gateway}/v1/chat/completions", body,
                                 {"Content-Type": "application/json", "x-bf-vk": key, "x-wb-call": call_id or f"reply-{time.time_ns()}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        for line in r:
            if stop is not None and stop.is_set():
                return
            line = line.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                return
            try:
                delta = json.loads(data)["choices"][0].get("delta") or {}
            except (ValueError, KeyError, IndexError):
                continue
            if delta.get("content"):
                yield delta["content"]


def split(reply: str) -> tuple[str, str | None]:
    """The spoken part and the handoff request (None when there is none)."""
    spoken, sep, rest = reply.partition("HANDOFF:")
    return spoken.strip(), (rest.strip() or None) if sep else None


MARKUP = re.compile(r"[*#`|_~]|^\s*([-•]|\d+[.)])\s", re.M)
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


def spoken_ok(text: str) -> bool:
    """Fit to be spoken: no markdown, list lines, emoji or code; at most three sentences and sixty words."""
    if not text or MARKUP.search(text) or EMOJI.search(text):
        return False
    sentences = [s for s in re.split(r"[.!?…]+(?:\s|$)", text) if s.strip()]
    return len(sentences) <= 3 and len(text.split()) <= 60


def run(card: dict, utterance: str, gateway: str, key: str, model: str, call_id: str = "") -> dict:
    """One case: the reply, its handoff, whether it is fit to speak, and time to the first word."""
    t0 = time.perf_counter()
    first, out = None, []
    for tok in stream(card, [], utterance, gateway, key, model, call_id):
        if first is None:
            first = (time.perf_counter() - t0) * 1000
        out.append(tok)
    spoken, handoff = split("".join(out))
    return {"utterance": utterance, "spoken": spoken, "handoff": handoff, "spoken_ok": spoken_ok(spoken),
            "first_token_ms": round(first) if first is not None else None}
