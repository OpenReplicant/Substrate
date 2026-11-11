"""The handler contract and its runner (README.md, "The contract"). No database here: the plugin records what
the runner returns.

A handler is a function registered with @handler(name). It takes (input, ask) and returns Answer, Escalate,
Waiting or Dropped. `ask(name, input)` calls another handler through the runner, so the nested call is recorded
too. Calling a registered handler any other way raises Unrecorded, and the runner records the call as refused.
"""
from __future__ import annotations

import contextvars
import functools
import time
from dataclasses import dataclass, field
from typing import Any, Callable

KINDS = ("script", "hook", "rule", "model", "session", "person")

# A kind's cost until a handler of it has been measured (README.md, "Rank"): seconds, usd, person.
PRIOR = {
    "rule": {"person": 0, "usd": 0, "seconds": 0.01},
    "script": {"person": 0, "usd": 0, "seconds": 1},
    "hook": {"person": 0, "usd": 0, "seconds": 1},
    "model": {"person": 0, "usd": 0.001, "seconds": 5},
    "session": {"person": 0, "usd": 0.1, "seconds": 60},
    "person": {"person": 1, "usd": 0, "seconds": 3600},
}


@dataclass
class Answer:
    value: Any
    confidence: float | None = None
    note: str | None = None


@dataclass
class Escalate:
    reason: str
    to: str | None = None


@dataclass
class Waiting:
    reason: str = "no answer yet"


@dataclass
class Dropped:
    reason: str = "the input went away"


class Unrecorded(RuntimeError):
    """A handler was called around the runner."""


REGISTRY: dict[str, Callable] = {}
_permit: contextvars.ContextVar[str | None] = contextvars.ContextVar("permit", default=None)


def handler(name: str):
    """Register fn as the handler `name`. The wrapper runs only when the runner has just permitted that name."""
    def wrap(fn):
        @functools.wraps(fn)
        def guarded(*a, **kw):
            if _permit.get() != name:
                raise Unrecorded(f"handler {name} was called around the runner (use ask)")
            _permit.set(None)
            return fn(*a, **kw)
        REGISTRY[name] = guarded
        return guarded
    return wrap


@dataclass
class Call:
    handler: str
    kind: str                      # answer, escalate, waiting, dropped, refused
    value: Any = None
    confidence: float | None = None
    reason: str | None = None
    to: str | None = None
    seconds: float = 0.0
    parent: int | None = None      # index of the call that asked for this one
    note: str | None = None


def check(result) -> str | None:
    """What is wrong with a handler's result, or None."""
    if isinstance(result, Answer):
        c = result.confidence
        if c is None or isinstance(c, bool) or not isinstance(c, (int, float)) or not 0 <= c <= 1:
            return f"an answer needs a confidence in [0, 1], got {c!r}"
        return None
    if isinstance(result, Escalate):
        return None if (result.reason or "").strip() else "an escalation needs a reason"
    if isinstance(result, (Waiting, Dropped)):
        return None
    return f"a handler returns Answer, Escalate, Waiting or Dropped, not {type(result).__name__}"


@dataclass
class Runner:
    """Takes one input up a route. `answers` is the stream's: final (the first answer ends the climb) or advisory
    (every handler on the route sees it, and an answer from a lower one is a recommendation)."""
    order: list[str]
    entries: dict[str, str]                    # handler slug -> registered name
    answers: str = "final"
    reveal: set = field(default_factory=set)   # handler slugs that may see the private fields (a person: it is their decision)
    private: tuple = ("outcome",)
    calls: list[Call] = field(default_factory=list)

    def _sees(self, slug: str, item):
        if not isinstance(item, dict) or slug in self.reveal:
            return item
        return {k: v for k, v in item.items() if k not in self.private}

    def _invoke(self, slug: str, item, parent: int | None) -> Call:
        name = self.entries.get(slug, slug)
        fn = REGISTRY.get(name)
        index = len(self.calls)
        self.calls.append(Call(slug, "refused", parent=parent))
        if fn is None:
            self.calls[index] = Call(slug, "refused", reason=f"no handler registered as {name!r}", parent=parent)
            return self.calls[index]

        def ask(other: str, other_input=None) -> Call:
            return self._invoke(other, item if other_input is None else other_input, index)

        t0 = time.perf_counter()
        token = _permit.set(name)
        try:
            result = fn(self._sees(slug, item), ask)
            problem = check(result)
        except Unrecorded as e:
            result, problem = None, str(e)
        except Exception as e:      # a handler that crashes escalates; the crash is the reason
            result, problem = None, f"{type(e).__name__}: {e}"
        finally:
            _permit.reset(token)
        seconds = time.perf_counter() - t0
        if problem:
            call = Call(slug, "refused", reason=problem, seconds=seconds, parent=parent)
        elif isinstance(result, Answer):
            call = Call(slug, "answer", value=result.value, confidence=float(result.confidence), seconds=seconds,
                        parent=parent, note=result.note)
        elif isinstance(result, Escalate):
            call = Call(slug, "escalate", reason=result.reason, to=result.to, seconds=seconds, parent=parent)
        else:
            call = Call(slug, "waiting" if isinstance(result, Waiting) else "dropped", reason=result.reason,
                        seconds=seconds, parent=parent)
        self.calls[index] = call
        return call

    def handle(self, item) -> list[Call]:
        """Climb the route; returns every call made, nested ones included, in the order made."""
        self.calls = []
        i = 0
        while i < len(self.order):
            slug = self.order[i]
            call = self._invoke(slug, item, None)
            if call.kind in ("waiting", "dropped"):
                break
            if call.kind == "answer" and self.answers == "final":
                break
            if call.kind == "escalate" and call.to in self.order[i + 1:]:
                i = self.order.index(call.to)      # escalation may skip rungs, never go down
                continue
            i += 1
        return self.calls


def rank_key(cost: dict) -> tuple:
    """A person's attention first, then money, then time (README.md, "Rank")."""
    return (cost.get("person", 0), cost.get("usd", 0), cost.get("seconds", 0))
