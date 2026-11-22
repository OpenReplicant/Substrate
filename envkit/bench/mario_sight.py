"""How well envkit.vision sees Super Mario Bros. 1-1, scored against the game's own memory (an answer key the agent
never gets: the camera at 0x71A/0x71C, the player's screen position at 0x3AD/0xCE, the five enemy slots at
0x0F, 0x6E/0x87, 0xCF). Plays a jumpy random policy with lives topped up so the recording stays in the level.

    NES_ROM=~/roms/smb.nes python3 -m envkit.bench.mario_sight [--steps 3000]
"""
from __future__ import annotations

import argparse
import collections
import os
import random
import time

import numpy as np

from envkit.nes import mask
from envkit.vision import Sight

TOP = 32
ACTS = [["right"], ["right", "A"], ["right", "B"], ["right", "A", "B"], ["A"], ["left"], []]
WEIGHTS = [2, 4, 2, 5, 1, 1, 1]


def record(rom, steps, seed=1):
    from nes_py import NESEnv
    e = NESEnv(rom)
    e.reset()
    for b, f in [["", 40], ["start", 10], ["", 160]]:
        for _ in range(f):
            e.step(mask(b))
    rng, a, hold = random.Random(seed), 0, 0
    r = lambda k: int(e.ram[k])  # noqa: E731
    for _ in range(steps):
        if hold == 0:
            a, hold = rng.choices(range(len(ACTS)), WEIGHTS)[0], rng.randint(2, 10)
        hold -= 1
        e.ram[0x75A] = 2  # lives topped up
        for _ in range(4):
            e.step(mask(ACTS[a]))
        cam = r(0x71A) * 256 + r(0x71C)
        ents = [(r(0x3AD), r(0xCE), r(0x0E) == 8 and r(0xB5) <= 1)] + [
            (r(0x6E + i) * 256 + r(0x87 + i) - cam, r(0xCF + i), bool(r(0x0F + i)) and r(0xB6 + i) <= 1)
            for i in range(5)]
        yield e.screen.copy(), cam, ents


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=3000)
    ap.add_argument("--warmup", type=int, default=300)
    a = ap.parse_args(argv)
    out = []

    class Bus:
        def publish(self, m, ch, data):
            out.append(data)

    class Msg:
        def __init__(self, data):
            self.data = data

    sight = Sight("sight", crop=[TOP, 0], dx=[-4, 12])
    sight._rt = Bus()
    n = collections.Counter()
    cams, areas, last, spent = [], [], [None, None], 0.0
    for t, (screen, cam, ents) in enumerate(record(os.environ["NES_ROM"], a.steps)):
        out.clear()
        t0 = time.perf_counter()
        sight.on("rgb", Msg(screen))
        spent += time.perf_counter() - t0
        seen, things = out
        cams.append((seen["x"], cam, seen["area"]))
        if t < a.warmup or seen["cut"]:
            continue
        x = seen["x"]
        boxes = [(h["box"][0] - x, h["box"][1], h["box"][2] - x, h["box"][3]) for h in things]
        truth = [(ex + 8, ey + 16, i) for i, (ex, ey, on) in enumerate(ents) if on and ey + 16 >= TOP and 0 <= ex < 248]
        near = lambda cx, cy, b: b[0] - 6 <= cx <= b[2] + 6 and b[1] - 10 <= cy <= b[3] + 10  # noqa: E731
        for cx, cy, i in truth:
            hit = [k for k, b in enumerate(boxes) if near(cx, cy, b)]
            n["player" if i == 0 else "enemy", bool(hit)] += 1
            if i == 0 and hit:
                pid = things[hit[0]]["id"]
                if last[0] == t - 1:
                    n["same id", pid == last[1]] += 1
                last[:] = [t, pid]
        for b, h in zip(boxes, things):
            if h["moved"]:
                n["precision", any(near(cx, cy, b) for cx, cy, _ in truth)] += 1
    est, true, area = (np.array(v) for v in zip(*cams))
    level = area == np.bincount(area).argmax()  # the other areas are the cards between lives
    lag = np.minimum(np.abs(est - true), np.abs(est - np.r_[true[0], true[:-1]]))[level]
    print(f"{a.steps} steps, sight {spent / a.steps * 1000:.1f} ms a step")
    print(f"camera: within 2 px of the game's {np.mean(lag <= 2):.3f}, worst {lag.max()} px, "
          f"{len(set(area.tolist()))} areas")
    for k in ("player", "enemy", "same id", "precision"):
        tot = n[k, True] + n[k, False]
        print(f"{k}: {n[k, True] / max(tot, 1):.3f} of {tot}")


if __name__ == "__main__":
    main()
