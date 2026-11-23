"""The voice head's router (S-170): does what the owner said need work, or can it be answered by talking?

Two ways, chosen by VOICE_ROUTER: `tools` (the default, at the end of this file) lets the fast model decide by the tool
it calls each turn; `embed` (the Router class) decides by a vote over example embeddings, a first pass for later.

"talk" goes to the fast model, which answers at once; "work" goes to the worker's queue (the slow local model, with
tools), and its answer is read out when it comes. The 1.7B fast model could not make this call itself (S-169: it
handed over everything, or with a constrained answer missed a quarter of the jobs); a nearest-example vote over
embeddings made it on the same utterances, in about 65 ms on the CPU. Examples are the seed below plus every
`voice.route.example` signal ({"text": ..., "route": "talk" | "work"}): a correction is one more example.

Standard library only; the embedder is passed in (the voice head's goes through the gateway).
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Callable

ROUTES = ("talk", "work")
# A prefix in the embedding model's instruction format (Qwen3-Embedding: "Instruct: ...\nQuery: ").
INSTRUCT = ("Instruct: Classify whether this spoken request needs tools (computer, files, saving, web) or can be "
            "answered by talking\nQuery: ")
SEED = [
    ("Hi there, what's up?", "talk"), ("How are you feeling today?", "talk"), ("That's funny, thanks!", "talk"),
    ("I had a long day at work.", "talk"), ("Can you cheer me up?", "talk"), ("Good night!", "talk"),
    ("What's the capital of Spain?", "talk"), ("How many legs does a spider have?", "talk"),
    ("What does photosynthesis mean?", "talk"), ("Give me a tip for sleeping better.", "talk"),
    ("How should I start learning the guitar?", "talk"), ("Say something nice.", "talk"),
    ("What's the difference between a frog and a toad?", "talk"), ("Do you like music?", "talk"),
    ("Open my calendar and see what's on Friday.", "work"), ("Remember that my sister's birthday is in June.", "work"),
    ("Search for cheap flights to Lisbon.", "work"), ("Draft an email to my landlord about the heating.", "work"),
    ("Look through my project folder and tell me what's unfinished.", "work"), ("Delete the old logs on my machine.", "work"),
    ("Is my backup still running?", "work"), ("Make a to-do list for the weekend and save it.", "work"),
    ("What's the weather forecast for tomorrow?", "work"), ("Run the tests and tell me what failed.", "work"),
    ("How much memory is the computer using?", "work"), ("Write me a one-page report on solar panels.", "work"),
    ("Add eggs to my shopping list.", "work"), ("Which files did I change today?", "work"),
]

Embed = Callable[[list[str]], list[list[float]]]


def _unit(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


class Router:
    """k nearest examples by cosine similarity; the majority route wins (k odd, so no ties)."""

    def __init__(self, embed: Embed, examples: list[tuple[str, str]] | None = None, k: int = 3):
        self.embed, self.k = embed, k
        self.examples: list[tuple[str, str]] = []
        self.vectors: list[list[float]] = []
        self.set_examples(examples if examples is not None else SEED)

    def set_examples(self, examples: list[tuple[str, str]]) -> None:
        examples = [(t.strip(), r) for t, r in examples if r in ROUTES and t and t.strip()]
        if not examples:
            raise ValueError("a router needs examples")
        vectors = [_unit(v) for v in self.embed([INSTRUCT + t for t, _ in examples])]
        self.examples, self.vectors = examples, vectors

    def route(self, text: str) -> tuple[str, dict]:
        """The route, and what decided it: the nearest examples with their similarity."""
        v = _unit(self.embed([INSTRUCT + text])[0])
        sims = sorted(((sum(a * b for a, b in zip(v, u)), i) for i, u in enumerate(self.vectors)), reverse=True)
        near = [(round(s, 3), *self.examples[i]) for s, i in sims[:self.k]]
        work = sum(1 for _, _, r in near if r == "work")
        route = "work" if work * 2 > len(near) else "talk"
        return route, {"near": [{"similarity": s, "text": t, "route": r} for s, t, r in near]}


# ---- the fast model decides, by the tool it calls (S-170, the owner's idea; S-171 adds quick tools): it is trained to
# call tools, so every step it must call one. talk ends the turn (spoken as it streams); delegate ends it too (the
# worker takes multi-step work); the quick tools (voice/tools.py) run in the voice head and their result comes back for
# the next step, at most QUICK_STEPS of them a turn, then only talk or delegate are offered. Measured on the trial's 12
# held-out utterances with talk, delegate and save_note: 12/12 twice, median 0.35 s, with thinking off,
# tool_choice required, a stop at </think> (with thinking off it sometimes writes plain words, then loops on that
# marker) and plain words taken as talk. Without save_note it said "Saved note: ..." for a note it had not saved.
QUICK_STEPS = 3
# the fast model's system prompt, a file of its own so Morphogen can judge a change to it alone (cell voice-route,
# S-193); {now} is filled per turn
TOOLS_SYSTEM = (Path(__file__).parent / "tools_system.txt").read_text().rstrip("\n")


def _fn(name: str, description: str, props: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {"name": name, "description": description,
                                             "parameters": {"type": "object", "properties": props, "required": required}}}


_S = {"type": "string"}
TALK = _fn("talk", "Say this to the owner out loud; ends the turn", {"text": {"type": "string", "description": "spoken words only"}}, ["text"])
DELEGATE = _fn("delegate", "Hand multi-step work to the assistant with more tools; ends the turn",
               {"task": {"type": "string", "description": "the request, complete and self-contained"}}, ["task"])
QUICK = [
    _fn("save_note", "Save a short note for the owner", {"text": _S}, ["text"]),
    _fn("read_notes", "Read the owner's notes, optionally only those about a topic", {"topic": _S}, []),
    _fn("remind", "Set a reminder", {"text": _S, "when": {"type": "string", "description": "YYYY-MM-DDTHH:MM local time, or 'in N minutes'"}}, ["text", "when"]),
    _fn("calculate", "Work out an arithmetic expression", {"expression": _S}, ["expression"]),
    _fn("lookup", "Look up a fact on Wikipedia", {"topic": _S}, ["topic"]),
    _fn("search", "Search the web", {"query": _S}, ["query"]),
]
TOOLS = [TALK, DELEGATE] + QUICK
QUICK_NAMES = {t["function"]["name"] for t in QUICK}
ENDS = {"talk", "delegate"}


def tools_body(model: str, history: list[dict], utterance: str | None, now: str = "", steps: list[dict] | None = None,
               final: bool = False, stream: bool = False) -> dict:
    """The request for one step: the history, the utterance, the steps so far this turn (assistant tool calls and
    their results); final offers only talk and delegate."""
    msgs = [{"role": "system", "content": TOOLS_SYSTEM.format(now=now or "unknown")}] + history
    if utterance is not None:
        msgs.append({"role": "user", "content": utterance})
    return {"model": model, "messages": msgs + (steps or []), "tools": [TALK, DELEGATE] if final else TOOLS,
            "tool_choice": "required", "temperature": 0.2, "max_tokens": 300, "reasoning_effort": "none",
            "stop": ["</think>"], "stream": stream}


def tools_decision(message: dict) -> tuple[str, str]:
    """(tool, its main text) from a whole reply: talk or delegate, or a quick tool with its arguments as JSON. Plain words
    with no tool call are talk; an unknown tool, bad arguments or nothing at all are ("", "")."""
    calls = message.get("tool_calls") or []
    if not calls:
        text = (message.get("content") or "").strip()
        return ("talk", text) if text else ("", "")
    f = calls[0].get("function") or {}
    try:
        args = json.loads(f.get("arguments") or "{}")
    except ValueError:
        return "", ""
    name = f.get("name")
    if not isinstance(args, dict) or name not in ENDS | QUICK_NAMES:
        return "", ""
    if name in QUICK_NAMES:
        return name, json.dumps(args)
    text = args.get("task" if name == "delegate" else "text")
    return (name, text.strip()) if isinstance(text, str) and text.strip() else ("", "")


class TalkText:
    """The value of "text" in a talk call's arguments, read as the arguments stream in: feed() returns what is new.
    JSON string escapes are decoded; a \\u escape split across chunks waits for its four digits."""

    def __init__(self):
        self.buf, self.pos, self.inside, self.done = "", 0, False, False

    def feed(self, chunk: str) -> str:
        self.buf += chunk
        out = []
        if not self.inside and not self.done:
            m = re.search(r'"text"\s*:\s*"', self.buf)
            if not m:
                return ""
            self.inside, self.pos = True, m.end()
        while self.inside and self.pos < len(self.buf):
            c = self.buf[self.pos]
            if c == '"':
                self.inside, self.done = False, True
                self.pos += 1
                break
            if c == "\\":
                if self.pos + 1 >= len(self.buf):
                    break
                e = self.buf[self.pos + 1]
                if e == "u":
                    if self.pos + 6 > len(self.buf):
                        break
                    try:
                        out.append(chr(int(self.buf[self.pos + 2:self.pos + 6], 16)))
                    except ValueError:
                        pass
                    self.pos += 6
                    continue
                out.append({"n": "\n", "t": "\t", "r": "", "b": "", "f": ""}.get(e, e))
                self.pos += 2
                continue
            out.append(c)
            self.pos += 1
        return "".join(out)


def stream_events(lines):
    """OpenAI chat-completion stream lines -> ("content", text) and ("tool", index, id, name, arguments-delta) events."""
    for line in lines:
        line = line.decode("utf-8", "replace").strip() if isinstance(line, bytes) else line.strip()
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
            yield ("content", delta["content"])
        for tc in delta.get("tool_calls") or []:
            f = tc.get("function") or {}
            yield ("tool", tc.get("index", 0), tc.get("id"), f.get("name"), f.get("arguments") or "")


_EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F\u200B-\u200D\u2060]")


def speakable(text: str) -> str:
    """Text fit for speech: markdown emphasis, headings, code marks, list marks and emoji removed (the model sometimes
    writes them in a talk call anyway)."""
    t = _EMOJI.sub("", text or "")
    t = re.sub(r"(?m)^\s*(?:[-*•]|\d+[.)])\s+", "", t)
    t = re.sub(r"[*_`#]+", "", t)
    return re.sub(r"\s+", " ", t).strip()


def note_name(text: str) -> str:
    from voice import tools
    return tools.note_name(text)
