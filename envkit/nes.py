"""NES games as worlds, from a declaration: the ROM, the buttons, how to get past the title screen, and what to
read from memory. Nothing about any one game is written here (envkit/declarations/mario.toml is one declaration).

The ROM is the owner's and is never stored with the code: a declaration names it "$NES_ROM" (or another variable)
and the machine supplies the path. nes-py runs mappers 0 to 3, which covers most early cartridges and many hacks
made from them; a ROM it can't run fails when the world starts, with nes-py's message.

    [[module]]
    driver = "nes"
    rom = "{rom}"
    frameskip = 4                       # emulator frames per step; the buttons are held for all of them
    start = [["start", 10], ["", 120]]  # once, before the first step: buttons, frames held (then saved and reused)
    progress = "x"                      # reward each step: how far this reading went up (optional)
    life = "lives"                      # a drop in this reading is a lost life: an event, and `attempt` goes up
    level = "stage"                     # a change in this reading is a level done: `levels_completed` goes up
    ends = [{ reading = "stage", changes = true }]   # the episode is over when any of these holds
    poke = [{ addr = 0x75A, value = 2, when = "{keep_lives}" }]   # memory written before every step: a world-side
                                        # setting (here, lives kept up), on when `when` is true

    [module.buttons]                    # the actions, in order: name -> buttons held
    noop = []
    right = ["right"]

    [module.readings]                   # screen is the picture; the rest are memory, by address (fair = false:
    screen = { type = "rgb" }           # a judged profile may withhold them)
    x = { ram = [0x6D, 0x86], type = "scalar", fair = false }   # several bytes read as one number, high first

Besides the declared readings a NES world always offers `attempt` (1, then one more each life lost) and
`levels_completed`: counts of what the player sees on the screen anyway, so they are fair under any profile.
"""
from __future__ import annotations

import numpy as np

from envkit.core import Module, Msg, Port, World

BUTTONS = {"right": 0x80, "left": 0x40, "down": 0x20, "up": 0x10, "start": 0x08, "select": 0x04, "B": 0x02, "A": 0x01}


def mask(buttons) -> int:
    out = 0
    for b in ([buttons] if isinstance(buttons, str) else buttons):
        if b:
            out |= BUTTONS[b]
    return out


class NESWorld(World):
    inputs = {"cmd": Port("command", keep="latest")}

    def __init__(self, name, rom: str, buttons: dict, readings: dict | None = None, frameskip: int = 4,
                 start: list | None = None, progress: str | None = None, life: str | None = None,
                 level: str | None = None, ends: list | None = None, poke: list | None = None,
                 max_steps: int = 5000, seed: int = 0, rate: float = 15.0):
        self.outputs = {"reward": Port("scalar", keep="all"), "actions": Port("event", keep="all"),
                        "event": Port("event", keep="all"), "tick": Port("event", keep="latest"),
                        "attempt": Port("scalar"), "levels_completed": Port("scalar")}
        self.ram_of, self.screen_port = {}, None
        for port, spec in (readings or {"screen": {"type": "rgb"}}).items():
            spec = dict(spec)
            addr = spec.pop("ram", None)
            if addr is None:
                self.screen_port = port
            else:
                self.ram_of[port] = [addr] if isinstance(addr, int) else list(addr)
            self.outputs[port] = Port(**spec)
        super().__init__(name)
        if not rom:
            raise FileNotFoundError(f"{name}: no ROM given (set the variable the declaration names, e.g. NES_ROM)")
        self.rom, self.names = rom, list(buttons)
        self.masks = [mask(buttons[n]) for n in self.names]
        self.frameskip, self.start_seq, self.max_steps = int(frameskip), list(start or []), int(max_steps)
        self.progress, self.life, self.level, self.ends = progress, life, level, list(ends or [])
        self.attempt, self.levels = 1, 0
        self.seed, self.rate = int(seed), rate
        self.poke = {int(p["addr"]): int(p["value"]) for p in (poke or []) if p.get("when", True)}
        self.env, self.cmd, self.steps, self.total, self.last = None, None, 0, 0.0, {}

    def start(self):
        from nes_py import NESEnv
        self.env = NESEnv(self.rom)
        self.env.reset()
        for buttons, frames in self.start_seq:
            for _ in range(int(frames)):
                self.env.step(mask(buttons))
        for _ in range(self.seed):  # a seed is a few idle frames more, so runs differ in timing only
            self.env.step(0)
        self.env._backup()  # a reset comes back here, past the title screen

    def read(self, port):
        v = 0
        for a in self.ram_of[port]:
            v = v * 256 + int(self.env.ram[a])
        return v

    def on(self, port: str, msg: Msg):
        if port == "cmd":
            self.cmd = msg.data

    def _emit_obs(self, now):
        if self.screen_port:
            self.emit(self.screen_port, self.env.screen.copy())
        for p, v in now.items():
            self.emit(p, v)
        self.emit("attempt", self.attempt)
        self.emit("levels_completed", self.levels)
        self.emit("tick", {"step": self.steps})

    def _end(self, now):
        for e in self.ends:
            v, was = now[e["reading"]], self.last.get(e["reading"])
            if "equals" in e and v == e["equals"]:
                return e
            if e.get("changes") and was is not None and v != was:
                return e
        return None

    def tick(self, t: int):
        if t == 0:
            self.env.reset()
            self.last = {p: self.read(p) for p in self.ram_of}
            self.emit("actions", {"names": self.names, "points": [False] * len(self.names)})
            self.emit("event", {"kind": "start", "seed": self.seed})
            self._emit_obs(self.last)
            return
        cmd, self.cmd = self.cmd, None
        i = self.names.index(cmd["action"]) if cmd else 0
        for a, v in self.poke.items():
            self.env.ram[a] = v
        for _ in range(self.frameskip):
            self.env.step(self.masks[i])
        self.steps += 1
        now = {p: self.read(p) for p in self.ram_of}
        r = 0.0
        if self.progress:
            d = now[self.progress] - self.last[self.progress]
            r = float(d) if abs(d) < 64 else 0.0  # a jump this big is a restart or a new area, not progress
        self.total += r
        if self.life and now[self.life] < self.last[self.life]:
            self.attempt += 1
            self.emit("event", {"kind": "life", "left": now[self.life], "step": self.steps})
        if self.level and now[self.level] != self.last[self.level]:
            self.levels += 1
            self.emit("event", {"kind": "level", "levels": self.levels, "step": self.steps})
        self.emit("reward", r)
        self._emit_obs(now)
        hit = self._end(now)
        self.last = now
        if hit or self.steps >= self.max_steps:
            self.done = True
            self.emit("event", {"kind": "end", "steps": self.steps, "return": self.total, "why": hit or "steps"})

    def stop(self):
        if self.env is not None:
            self.env.close()


class Quantize(Module):
    """An encoder: an RGB screen to a small grid of colour indices, the form the atlas reads. Each block of
    `block` pixels becomes its most common colour; colours get indices in the order first seen (so the same
    picture always gives the same grid within a run), and past 16 a new colour takes the nearest one's index."""
    kind = "encoder"
    inputs = {"rgb": Port("rgb")}
    outputs = {"grid": Port("grid16")}

    def __init__(self, name, block: int = 4, crop: list | None = None):
        super().__init__(name)
        self.block, self.crop, self.colours = int(block), crop, []

    def index(self, c):
        for i, k in enumerate(self.colours):
            if k == c:
                return i
        if len(self.colours) < 16:
            self.colours.append(c)
            return len(self.colours) - 1
        d = [sum((a - b) ** 2 for a, b in zip(k, c)) for k in self.colours]
        return int(np.argmin(d))

    def on(self, port, msg):
        img = np.asarray(msg.data)
        if self.crop:
            top, bottom = self.crop
            img = img[top:img.shape[0] - bottom]
        b = self.block
        h, w = img.shape[0] // b, img.shape[1] // b
        packed = img[:h * b, :w * b].astype(np.int64) @ np.array([65536, 256, 1])
        vals, inv = np.unique(packed, return_inverse=True)
        lut = np.array([self.index((v >> 16, (v >> 8) & 255, v & 255)) for v in vals.tolist()])
        idx = lut[inv.reshape(packed.shape)]  # each pixel's colour index
        block = (np.arange(h * b)[:, None] // b) * w + np.arange(w * b)[None, :] // b
        counts = np.bincount((block * 16 + idx).ravel(), minlength=h * w * 16).reshape(h * w, 16)
        self.emit("grid", counts.argmax(1).reshape(h, w))
