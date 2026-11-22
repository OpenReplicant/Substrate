"""Modules, channels and the two schedulers (README.md). The standard library only.

A module is an actor: it reads messages on its input ports and writes messages on its output ports, and keeps no
state anyone else can touch. Each port is bound to a channel by name; the scheduler delivers what is published on
a channel to every port bound to it. Worlds are the modules the clock drives: the scheduler calls `tick` on them,
everything else acts only when a message arrives.
"""
from __future__ import annotations

import collections
import threading
import time
from dataclasses import dataclass, field
from typing import Any

TYPES = {"grid16", "rgb", "depth", "labels", "scalar", "text", "command", "event", "json"}


@dataclass(frozen=True)
class Msg:
    channel: str
    t: int  # the environment's clock, in ticks
    seq: int  # order within the run
    source: str  # the module that wrote it
    data: Any


@dataclass
class Port:
    type: str = "json"
    keep: str = "latest"  # latest: only the newest matters (a frame); all: every message matters (chat, events)
    fair: bool = True  # world readings only: may an agent under a judged profile read it
    doc: str = ""

    def __post_init__(self):
        if self.type not in TYPES:
            raise ValueError(f"unknown port type {self.type!r}")
        if self.keep not in ("latest", "all"):
            raise ValueError(f"unknown keep policy {self.keep!r}")


class Module:
    """Subclasses declare `inputs` and `outputs` (port name -> Port) and override `on` (and `tick` for worlds)."""
    kind = "module"  # world, encoder, agent, tap

    def __init__(self, name: str):
        self.name = name
        self.inputs: dict[str, Port] = dict(getattr(self, "inputs", {}))
        self.outputs: dict[str, Port] = dict(getattr(self, "outputs", {}))
        self.wired_in: dict[str, str] = {}  # input port -> channel
        self.wired_out: dict[str, str] = {}  # output port -> channel
        self._rt = None

    def emit(self, port: str, data: Any):
        if port not in self.outputs:
            raise KeyError(f"{self.name} has no output port {port!r}")
        self._rt.publish(self, self.wired_out.get(port, f"{self.name}.{port}"), data)

    def start(self):
        pass

    def on(self, port: str, msg: Msg):
        pass

    def stop(self):
        pass


class World(Module):
    kind = "world"
    rate = 30.0  # steps a second under the realtime scheduler
    done = False

    def tick(self, t: int):
        """Advance one step with the latest commands received, and emit what is observed."""


class Environment:
    """Modules and their wiring. `expose` names the channels the environment offers to what is attached to it
    (agents, taps, a parent environment); `profiles` say which exposed readings are fair for which use."""

    def __init__(self, name: str, modules: list[Module], expose: dict[str, str] | None = None,
                 profiles: dict[str, list[str]] | None = None, doc: str = ""):
        self.name, self.modules, self.doc = name, modules, doc
        self.expose = dict(expose or {})
        self.profiles = dict(profiles or {})

    def port(self, exposed: str) -> tuple[Module, str, Port, str]:
        """The module, port name, Port and direction ('out' or 'in') behind an exposed name."""
        mod, _, pname = self.expose[exposed].partition(".")
        m = next(m for m in self.modules if m.name == mod)
        if pname in m.outputs:
            return m, pname, m.outputs[pname], "out"
        return m, pname, m.inputs[pname], "in"

    def channel(self, exposed: str) -> str:
        m, pname, _, d = self.port(exposed)
        return (m.wired_out if d == "out" else m.wired_in).get(pname, f"{m.name}.{pname}")

    def fair(self, exposed: str, profile: str | None) -> bool:
        if profile is None:
            return True
        allowed = self.profiles.get(profile)
        if allowed is None:
            raise KeyError(f"environment {self.name} has no profile {profile!r}")
        m, pname, port, d = self.port(exposed)
        return d == "in" or (exposed in allowed and port.fair)


def attach(env: Environment, module: Module, wiring: dict[str, str], profile: str | None = None):
    """Bind a module's ports to the environment's exposed names (module port -> exposed name). An agent may read
    only what the profile allows; anything may write to an exposed input (an agent's commands)."""
    for port, exposed in wiring.items():
        if port in module.inputs:
            if module.kind in ("agent", "workspace") and not env.fair(exposed, profile):
                raise PermissionError(f"{exposed} is not fair under profile {profile!r}")
            module.wired_in[port] = env.channel(exposed)
        elif port in module.outputs:
            module.wired_out[port] = env.channel(exposed)
        else:
            raise KeyError(f"{module.name} has no port {port!r}")


def nest(parent_name: str, child: Environment) -> list[Module]:
    """A child environment's modules, renamed under the parent ('child/module') with their channels renamed to
    match, so a parent can hold a child and wire to its exposed names (`child_channel`)."""
    out = []
    for m in child.modules:
        old = m.name
        m.name = f"{parent_name}/{old}"
        for d in (m.wired_in, m.wired_out):
            for p, ch in list(d.items()):
                d[p] = f"{parent_name}/{ch}"
        for p in m.inputs:
            m.wired_in.setdefault(p, f"{parent_name}/{old}.{p}")
        for p in m.outputs:
            m.wired_out.setdefault(p, f"{parent_name}/{old}.{p}")
        out.append(m)
    return out


class _Runtime:
    def __init__(self, modules: list[Module]):
        self.modules = modules
        self.worlds = [m for m in modules if isinstance(m, World)]
        self.subs = collections.defaultdict(list)  # channel -> [(module, port)]
        for m in modules:
            for p in m.inputs:
                self.subs[m.wired_in.get(p, f"{m.name}.{p}")].append((m, p))
            m._rt = self
        self.t, self.seq = 0, 0
        self.lock = threading.Lock()

    def _msg(self, source, channel, data):
        with self.lock:
            self.seq += 1
            return Msg(channel, self.t, self.seq, source.name, data)


class Lockstep(_Runtime):
    """Deterministic: each tick the worlds step, then messages are delivered until nothing more is emitted.
    Delivery is depth first: what a module emits while handling a message is delivered before the next message in
    the queue, so an encoder's output reaches an agent before the world's `tick` that follows the reading."""

    def __init__(self, modules):
        super().__init__(modules)
        self.queue = collections.deque()
        self.fresh = None  # messages emitted while one is being delivered

    def publish(self, source, channel, data):
        (self.queue if self.fresh is None else self.fresh).append(self._msg(source, channel, data))

    def run(self, max_ticks: int | None = None):
        for m in self.modules:
            m.start()
        try:
            while not all(w.done for w in self.worlds) and (max_ticks is None or self.t < max_ticks):
                for w in self.worlds:
                    if not w.done:
                        w.tick(self.t)
                while self.queue:
                    msg = self.queue.popleft()
                    self.fresh = []
                    for m, p in self.subs.get(msg.channel, ()):
                        m.on(p, msg)
                    self.queue.extendleft(reversed(self.fresh))
                    self.fresh = None
                self.t += 1
        finally:
            for m in self.modules:
                m.stop()
        return self.t


class Realtime(_Runtime):
    """On the wall clock: worlds step at their rates with whatever command is latest; every other module has its
    own thread and mailbox, so a slow one falls behind instead of holding the world up (on a `latest` port it
    sees only the newest message when it gets round to it)."""

    def __init__(self, modules, speed: float = 1.0):
        super().__init__(modules)
        self.speed = speed
        self.boxes = {m.name: collections.OrderedDict() for m in modules if not isinstance(m, World)}
        self.cv = threading.Condition()
        self.stopping = False

    def publish(self, source, channel, data):
        msg = self._msg(source, channel, data)
        with self.cv:
            for m, p in self.subs.get(channel, ()):
                if isinstance(m, World):
                    m.on(p, msg)  # worlds only store commands; cheap, done at once
                    continue
                box = self.boxes[m.name]
                k = (p, msg.seq) if m.inputs[p].keep == "all" else (p, None)
                box.pop(k, None)
                box[k] = msg
            self.cv.notify_all()

    def _worker(self, m):
        box = self.boxes[m.name]
        while True:
            with self.cv:
                while not box and not self.stopping:
                    self.cv.wait(0.1)
                if self.stopping and not box:
                    return
                (p, _), msg = box.popitem(last=False)
            m.on(p, msg)

    def run(self, seconds: float | None = None):
        for m in self.modules:
            m.start()
        threads = [threading.Thread(target=self._worker, args=(m,), daemon=True)
                   for m in self.modules if not isinstance(m, World)]
        for th in threads:
            th.start()
        t0 = time.monotonic()
        nxt = {w.name: t0 for w in self.worlds}
        try:
            while not all(w.done for w in self.worlds) and (seconds is None or time.monotonic() - t0 < seconds):
                now = time.monotonic()
                for w in self.worlds:
                    if not w.done and now >= nxt[w.name]:
                        w.tick(self.t)
                        nxt[w.name] += 1.0 / (w.rate * self.speed)
                self.t += 1
                time.sleep(max(0.0, min(nxt.values()) - time.monotonic()))
        finally:
            with self.cv:
                self.stopping = True
                self.cv.notify_all()
            for th in threads:
                th.join(timeout=5)
            for m in self.modules:
                m.stop()
        return self.t
