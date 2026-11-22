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

import math
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


# ---- the fast model decides, by the tool it calls (S-170, the owner's idea): it is trained to call tools, so every turn
# it must call one of these instead of choosing between plain words and a HANDOFF line. Measured on the trial's 12
# held-out utterances: 12/12 and 11/12 right, median 0.35 s, with thinking off, tool_choice required, a stop at
# </think> (with thinking off it sometimes writes plain words and then loops on that marker) and plain words taken as
# talk. Without save_note it said "Saved note: ..." for a note it had not saved.
TOOLS_SYSTEM = """You are the owner's companion, speaking with them out loud. Every turn, call exactly one tool.
talk: say your answer yourself, in one to three short spoken sentences (no lists, markdown or emoji). Use it for
greetings, small talk, feelings, quick facts, jokes, translations and simple advice.
delegate: hand the request to the assistant that has tools, when it needs the owner's computer, files or notes,
changing anything, the web or news, or a long written plan. Pass the request, complete.
save_note: save a short note or reminder the owner asks you to keep; then it is done.
Never say you did something (saved, checked, looked up) unless a tool did it, and never tell the owner you cannot
do something or have no tool for it: if you cannot answer it yourself, delegate it. Do not repeat the question back.
What you hear is a speech-to-text transcript and may have small mistakes; if it makes no sense, ask once."""
TOOLS = [
    {"type": "function", "function": {"name": "talk", "description": "Say this to the owner out loud",
     "parameters": {"type": "object", "properties": {"text": {"type": "string", "description": "what to say, spoken words only"}},
                    "required": ["text"]}}},
    {"type": "function", "function": {"name": "delegate", "description": "Hand a task that needs tools to the assistant with tools",
     "parameters": {"type": "object", "properties": {"task": {"type": "string", "description": "the request, complete and self-contained"}},
                    "required": ["task"]}}},
    {"type": "function", "function": {"name": "save_note", "description": "Save a short note or reminder for the owner",
     "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}},
]


def tools_body(model: str, history: list[dict], utterance: str) -> dict:
    """The request the voice head sends (OpenAI chat completions, through the gateway)."""
    return {"model": model, "messages": [{"role": "system", "content": TOOLS_SYSTEM}] + history + [{"role": "user", "content": utterance}],
            "tools": TOOLS, "tool_choice": "required", "temperature": 0.2, "max_tokens": 300, "reasoning_effort": "none",
            "stop": ["</think>"]}


def tools_decision(message: dict) -> tuple[str, str]:
    """(tool, its text) from the model's reply: talk, delegate or save_note. Plain words with no tool call are talk;
    an unknown tool, bad arguments or nothing at all are ("", "")."""
    import json
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
    text = args.get("task" if name == "delegate" else "text") if isinstance(args, dict) else None
    return (name, text.strip()) if name in ("talk", "delegate", "save_note") and isinstance(text, str) and text.strip() else ("", "")


def note_name(text: str) -> str:
    """A file name for a note: its first few words, lower case, hyphenated (the example plan's [\\w-]+)."""
    import re
    words = re.findall(r"[a-z0-9]+", text.lower())[:5]
    return "-".join(words) or "note"
