"""The workspace: one current picture of the situation, which detectors and agents post into and agents read.
Mechanics only; what to post, what is salient and what to do about it are the posters' and the agent's.

An entry is a symbol with provenance:

    {"key": "thing:644", "kind": "thing", "attrs": {...}, "source": "sight", "t": 120, "conf": 1.0, "ttl": 3}

- **binding**: entries with the same key are one thing. A later post merges its attributes into the entry; each
  attribute remembers which source set it and when, so two detectors describing the same thing make one entry.
- **staleness**: an entry not posted for `ttl` ticks is dropped (None: kept until retracted). A post with
  `"retract": true` drops it at once.
- **confidence**: kept per entry as posted; a claim and an observation of the same key sit side by side as two
  attributes with their sources until a poster settles it.
- **capacity**: `focus` is the `capacity` entries with the highest salience (posted, else 0), newest first among
  equals: a small view on purpose, since what gets in is attention.

Ports: `post` (in, all: an entry or a list of entries, from anyone), `tick` (in: the world's step is over; the
workspace then emits), `state` (out: every live entry), `focus` (out), `changed` (out: keys added, updated,
dropped since the last tick).
"""
from __future__ import annotations

from envkit.core import Module, Port


class Workspace(Module):
    kind = "workspace"

    def __init__(self, name, capacity: int = 12):
        self.inputs = {"post": Port("json", keep="all"), "tick": Port("event")}
        self.outputs = {"state": Port("json"), "focus": Port("json"), "changed": Port("event", keep="all")}
        super().__init__(name)
        self.capacity, self.entries, self.t = int(capacity), {}, 0
        self.added, self.updated, self.dropped = set(), set(), set()

    def put(self, e: dict, t: int):
        key = e["key"]
        if e.get("retract"):
            if self.entries.pop(key, None) is not None:
                self.dropped.add(key)
            return
        cur = self.entries.get(key)
        src = e.get("source", "?")
        if cur is None:
            cur = self.entries[key] = {"key": key, "kind": e.get("kind", key.split(":")[0]), "attrs": {}, "by": {},
                                       "t": t, "conf": e.get("conf", 1.0), "ttl": e.get("ttl"), "salience": 0.0}
            self.added.add(key)
        else:
            self.updated.add(key)
        for k, v in (e.get("attrs") or {}).items():
            cur["attrs"][k] = v
            cur["by"][k] = (src, t)
        cur["t"] = t
        for k in ("conf", "ttl", "salience", "kind"):
            if k in e:
                cur[k] = e[k]

    def on(self, port, msg):
        if port == "post":
            for e in msg.data if isinstance(msg.data, list) else [msg.data]:
                self.put(e, msg.t)
        elif port == "tick":
            self.t = msg.t
            for key, e in list(self.entries.items()):
                if e["ttl"] is not None and msg.t - e["t"] >= e["ttl"]:
                    del self.entries[key]
                    self.dropped.add(key)
            live = list(self.entries.values())
            self.emit("state", {"t": msg.t, "entries": live})
            self.emit("focus", sorted(live, key=lambda e: (-e["salience"], -e["t"]))[: self.capacity])
            if self.added or self.updated or self.dropped:
                self.emit("changed", {"t": msg.t, "added": sorted(self.added), "updated": sorted(self.updated - self.added),
                                      "dropped": sorted(self.dropped)})
            self.added, self.updated, self.dropped = set(), set(), set()


def by_kind(state: dict, kind: str) -> list[dict]:
    """The live entries of one kind, from a `state` message."""
    return [e for e in state["entries"] if e["kind"] == kind]


def one(state: dict, key: str) -> dict | None:
    return next((e for e in state["entries"] if e["key"] == key), None)


class Poster(Module):
    """An adapter: turns one channel's messages into workspace entries with a named function
    (`fn(data, t) -> [entries]`, found by "module:function"), so a detector needn't know the workspace exists."""
    kind = "encoder"

    def __init__(self, name, fn: str, source: str | None = None):
        import importlib
        self.inputs = {"in": Port("json", keep="all")}
        self.outputs = {"post": Port("json", keep="all")}
        super().__init__(name)
        mod, _, f = fn.partition(":")
        self.fn, self.source = getattr(importlib.import_module(mod), f), source or name

    def on(self, port, msg):
        es = self.fn(msg.data, msg.t)
        for e in es:
            e.setdefault("source", self.source)
        if es:
            self.emit("post", es)


# --- adapters for the standard detectors ------------------------------------------------------------------------

def things(data, t):
    """sight's things: one entry per tracked thing, gone the first tick it isn't seen."""
    return [{"key": f"thing:{th['id']}", "kind": "thing", "ttl": 1,
             "attrs": {k: th[k] for k in ("box", "kind", "v", "px", "moved", "mobile") if k in th}} for th in data]


def camera(data, t):
    return [{"key": "camera", "kind": "camera", "attrs": dict(data)}]


def scalar(name):
    def post(data, t):
        return [{"key": name, "kind": "reading", "attrs": {"value": data}}]
    return post


attempt = scalar("attempt")
reward = scalar("reward")
levels = scalar("levels_completed")


def event(data, t):
    return [{"key": f"event:{t}:{data.get('kind')}", "kind": "event", "ttl": 30, "salience": 1.0, "attrs": dict(data)}]


def observation(state: dict) -> dict:
    """The observation a things-reading agent (atlas/mover.py) expects, read out of a workspace state."""
    things = []
    for e in by_kind(state, "thing"):
        th = dict(e["attrs"])
        th["id"] = int(e["key"].split(":")[1])
        things.append(th)
    cam = one(state, "camera")
    obs = {"things": things, "camera": cam["attrs"] if cam else None}
    for k in ("attempt", "reward", "levels_completed"):
        e = one(state, k)
        if e is not None:
            obs[k] = e["attrs"]["value"]
    return obs
