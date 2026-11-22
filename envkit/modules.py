"""Standard modules: a world that runs any Gymnasium environment, an agent that wraps a step-by-step policy, and a
tap that records. Drivers are found by name in DRIVERS (declare.py builds them from a declaration)."""
from __future__ import annotations

import importlib
from typing import Any, Callable

import numpy as np

from envkit.core import Module, Msg, Port, World


def jsonable(v):
    if isinstance(v, np.ndarray):
        return v
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    return v


class GymWorld(World):
    """A Gymnasium environment as a world. Readings: one output port per declared observation key (a Dict
    observation's key, or "." for the whole observation), plus `reward` (scalar), `actions` (the action names and
    which take a point, once at the start), `event` (start, end) and `tick` (after each step's readings, so a reader
    can act on a complete observation). Input: `cmd`, a command
    {"action": name, "params": {...}}; with no command since the last step the world does nothing (or its
    declared no-op)."""

    inputs = {"cmd": Port("command", keep="latest")}

    def __init__(self, name, make: str, id: str, seed: int = 0, kwargs: dict | None = None,
                 readings: dict | None = None, noop: str | None = None, rate: float = 30.0):
        self.outputs = {"reward": Port("scalar", keep="all"), "actions": Port("event", keep="all"),
                        "event": Port("event", keep="all"), "tick": Port("event", keep="latest")}
        self.readings = {}
        for port, spec in (readings or {".": {"type": "json"}}).items():
            spec = dict(spec)
            self.readings[port] = spec.pop("key", port)
            self.outputs[port] = Port(**spec)
        super().__init__(name)
        mod, _, fn = make.partition(":")
        self.maker: Callable = getattr(importlib.import_module(mod), fn)
        self.id, self.seed, self.kwargs, self.noop, self.rate = id, int(seed), dict(kwargs or {}), noop, rate
        self.env, self.cmd, self.steps, self.total = None, None, 0, 0.0

    def start(self):
        self.env = self.maker(self.id, **self.kwargs)

    def _actions(self):  # read after a reset: some environments know their actions only then
        u = self.env.unwrapped
        self.names = u.action_names() if hasattr(u, "action_names") else [str(i) for i in range(self.env.action_space.n)]
        self.points = [bool(u.takes_point(i)) if hasattr(u, "takes_point") else False for i in range(len(self.names))]

    def on(self, port: str, msg: Msg):
        if port == "cmd":
            self.cmd = msg.data

    def _emit_obs(self, obs):
        for port, k in self.readings.items():
            self.emit(port, jsonable(obs if k == "." else obs[k]))
        self.emit("tick", {"step": max(self.steps, 0)})  # this step's readings are all out

    def tick(self, t: int):
        if self.steps == 0 and self.cmd is None and t == 0:
            obs, _ = self.env.reset(seed=self.seed)
            self._actions()
            self.emit("actions", {"names": self.names, "points": self.points})
            self.emit("event", {"kind": "start", "seed": self.seed})
            self._emit_obs(obs)
            self.steps = -1  # reset done, no step yet
            return
        cmd, self.cmd = self.cmd, None
        if cmd is None:
            if self.noop is None:
                return
            cmd = {"action": self.noop}
        u = self.env.unwrapped
        if hasattr(u, "set_params"):
            u.set_params(cmd.get("params") or {})
        obs, reward, terminated, truncated, info = self.env.step(self.names.index(cmd["action"]))
        self.steps = max(self.steps, 0) + 1
        self.total += float(reward)
        self.emit("reward", float(reward))
        self._emit_obs(obs)
        if terminated or truncated:
            self.done = True
            self.emit("event", {"kind": "end", "steps": self.steps, "return": self.total,
                                "terminated": bool(terminated)})

    def stop(self):
        if self.env is not None:
            self.env.close()


class PolicyAgent(Module):
    """A step-by-step policy as an agent. Its input ports are named by the observation keys the policy reads;
    `actions` (the world's action list) builds the policy; a message on `trigger` (the world's tick, or a
    workspace's state) asks it for a command, from the latest message on every other port and the trigger's own
    message under its name. A policy with `posts()` has what it returns emitted on `post` (claims for a workspace)."""
    kind = "agent"

    def __init__(self, name, build: Callable[[dict], Any], observe: list[str], trigger: str = "tick"):
        self.inputs = {"actions": Port("event", keep="all"), trigger: Port("event"), **{k: Port("json") for k in observe}}
        self.outputs = {"cmd": Port("command"), "why": Port("text"), "post": Port("json", keep="all")}
        super().__init__(name)
        self.build, self.trigger, self.policy, self.latest, self.observe = build, trigger, None, {}, list(observe)

    def on(self, port: str, msg: Msg):
        if port == "actions":
            self.policy = self.build(msg.data)
            return
        if port != self.trigger:
            self.latest[port] = msg.data
        elif self.policy is not None and all(k in self.latest for k in self.observe if k in self.wired_in):
            # under the realtime scheduler a tick can come before an encoder's first output: wait for it
            name, params = self.policy.step(dict(self.latest) | {self.trigger: msg.data})
            self.emit("cmd", {"action": name, "params": params})
            if getattr(self.policy, "why", None):
                self.emit("why", self.policy.why)
            posts = self.policy.posts() if hasattr(self.policy, "posts") else None
            if posts:  # the policy's own claims, for a workspace
                self.emit("post", posts)


class Recorder(Module):
    """A tap: keeps every message on its ports, in order. Nothing it does reaches a world."""
    kind = "tap"

    def __init__(self, name, ports: list[str], keep_data: Callable[[str, Any], bool] | None = None):
        self.inputs = {p: Port("json", keep="all") for p in ports}
        super().__init__(name)
        self.log, self.keep_data = [], keep_data

    def on(self, port: str, msg: Msg):
        data = msg.data if self.keep_data is None or self.keep_data(port, msg.data) else None
        self.log.append((msg.t, port, data))


class ScriptedChat(World):
    """A stand-in audience: says its lines in order, one every `every` ticks, then goes quiet. Reads `reply` (what
    the agent says back) and keeps it, so a run can show the conversation."""

    inputs = {"reply": Port("text", keep="all")}
    outputs = {"line": Port("text", keep="all")}

    def __init__(self, name, lines: list[str], every: int = 50, rate: float = 1.0):
        super().__init__(name)
        self.lines, self.every, self.rate, self.heard, self.k = list(lines), int(every), rate, [], 0

    def on(self, port, msg):
        self.heard.append((msg.t, msg.data))

    def tick(self, t):
        if t % self.every == 0 and self.k < len(self.lines):
            self.emit("line", {"user": f"viewer{self.k % 3}", "text": self.lines[self.k]})
            self.k += 1
        self.done = self.k >= len(self.lines) and t > self.every * len(self.lines)


from envkit.nes import NESWorld, Quantize  # noqa: E402  (nes-py itself is imported only when a NES world starts)
from envkit.vision import Sight  # noqa: E402
from envkit.workspace import Poster, Workspace  # noqa: E402
from envkit.org import OrgWorld  # noqa: E402

DRIVERS = {"gym": GymWorld, "chat": ScriptedChat, "nes": NESWorld, "quantize": Quantize, "sight": Sight,
           "workspace": Workspace, "poster": Poster, "org": OrgWorld}
