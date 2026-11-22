"""Seeing from the screen alone, for 2D games: where the camera is, what is background, what the things are, and
which thing is which from one frame to the next. Hand-written and exact, for pixel art (sprites repeat pixel for
pixel); for 3D games these slots take pre-made models instead (envkit/README.md, "Drivers and taps so far").

Everything works on frames of colour indices (`Palette` turns an RGB screen into them). Positions are in world
pixels: the camera's position plus the position on screen. Nothing here knows any particular game; a declaration
gives the play area (rows of HUD to leave out) and how far the camera can move in one step.
"""
from __future__ import annotations

import hashlib

import numpy as np

from envkit.core import Module, Port

UNKNOWN = 255


class Palette:
    """RGB to colour indices, numbered in the order first seen, so a run's indices never change."""

    def __init__(self):
        self.of = {}

    def __call__(self, rgb):
        s = np.asarray(rgb).astype(np.int64) @ np.array([65536, 256, 1])
        vals, inv = np.unique(s, return_inverse=True)
        lut = np.array([self.of.setdefault(int(v), len(self.of)) for v in vals.tolist()])
        return lut[inv.reshape(s.shape)].astype(np.uint8)


def components(mask: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
    """The 8-connected regions of a boolean image, each as (rows, cols). Runs per row, joined by union-find."""
    parent = []

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    runs, prev = [], []  # runs: (row, start, end, id)
    for y in range(mask.shape[0]):
        row = np.concatenate(([0], mask[y].astype(np.int8), [0]))
        d = np.flatnonzero(np.diff(row))
        cur = []
        for a, b in zip(d[::2], d[1::2]):
            i = len(parent)
            parent.append(i)
            for (_, pa, pb, j) in prev:
                if pa <= b and a <= pb:  # touching, diagonals included
                    ri, rj = find(i), find(j)
                    if ri != rj:
                        parent[ri] = rj
            cur.append((y, a, b, i))
        runs += cur
        prev = cur
    groups = {}
    for y, a, b, i in runs:
        groups.setdefault(find(i), []).append((y, a, b))
    out = []
    for rs in groups.values():
        ys = np.concatenate([np.full(b - a, y) for y, a, b in rs])
        xs = np.concatenate([np.arange(a, b) for y, a, b in rs])
        out.append((ys, xs))
    return out


class Camera:
    """Where the screen is in the world. Each step the frame is matched against the last one over the declared
    range of moves; the best match is the move (ties go to the smallest). When nothing matches well (a death, a
    door, a new room) the frame is looked up in the map of everything seen so far, so the same place keeps the same
    world position across lives; a frame found nowhere starts a new area."""

    def __init__(self, dx=(-8, 8), dy=(0, 0), good=0.9, width=16384):
        self.dx, self.dy, self.good, self.width = range(dx[0], dx[1] + 1), range(dy[0], dy[1] + 1), good, width
        self.prev, self.x, self.y, self.area, self.maps = None, 0, 0, 0, {}

    @staticmethod
    def _match(a, b, dx, dy):
        """The share of pixels equal when b is a moved by (dx, dy): b[y, x] == a[y + dy, x + dx]."""
        h, w = a.shape
        ya, yb = (dy, 0) if dy >= 0 else (0, -dy)
        xa, xb = (dx, 0) if dx >= 0 else (0, -dx)
        hh, ww = h - abs(dy), w - abs(dx)
        if hh <= 0 or ww <= 0:
            return 0.0
        return float((a[ya:ya + hh:2, xa:xa + ww] == b[yb:yb + hh:2, xb:xb + ww]).mean())

    def _map(self):
        return self.maps.setdefault(self.area, np.full((self.prev.shape[0], self.width), UNKNOWN, np.uint8))

    def _paint(self, f):
        m = self._map()
        x0 = max(self.x, 0)
        m[:, x0:x0 + f.shape[1]] = f[:, : max(0, min(f.shape[1], self.width - x0))]

    def _locate(self, f):
        """The best place for frame f in any area's map, if it fits well."""
        best = (0.0, None, None)
        for area, m in self.maps.items():
            seen = np.flatnonzero((m != UNKNOWN).any(0))
            if not len(seen):
                continue
            for x in range(0, int(seen[-1]) + 1, 1):
                win = m[::2, x:x + f.shape[1]]
                if win.shape[1] < f.shape[1] // 2:
                    break
                known = win != UNKNOWN
                if known.mean() < 0.5:
                    continue
                s = float((win[known] == f[::2, :win.shape[1]][known]).mean()) * known.mean()
                if s > best[0]:
                    best = (s, area, x)
        return best

    def __call__(self, f: np.ndarray):
        """f: a frame of colour indices (play area only). Returns (x, y, area, cut)."""
        cut = False
        if self.prev is not None:
            scores = [(self._match(self.prev, f, dx, dy), -abs(dx) - abs(dy), dx, dy) for dy in self.dy for dx in self.dx]
            s, _, dx, dy = max(scores)
            if s >= self.good:
                self.x, self.y = self.x + dx, self.y + dy
            else:
                cut = True
                ls, area, x = self._locate(f)
                if ls >= self.good:
                    self.area, self.x = area, x
                else:
                    self.area, self.x = max(self.maps) + 1, 0
        self.prev = f
        self._paint(f)
        return self.x, self.y, self.area, cut


def kind_of(patch: np.ndarray) -> str:
    """A thing's kind: its pixels (colours, with background as -1), the same whichever way it faces."""
    shape = str(patch.shape).encode()
    a, b = patch.tobytes() + shape, patch[:, ::-1].tobytes() + shape
    return hashlib.sha1(min(a, b)).hexdigest()[:8]


class Background:
    """What the world looks like with nothing on it: per world pixel, a running majority vote of the colours seen
    there. A pixel that disagrees with a settled vote belongs to a thing. Pixels inside a thing that has moved are
    not voted on, so a player standing still for a long time stays a thing instead of becoming scenery."""

    def __init__(self, settle=3, width=16384):
        self.settle, self.width, self.val, self.count = settle, width, {}, {}

    def _views(self, f, x, area):
        if area not in self.val:
            self.val[area] = np.full((f.shape[0], self.width), UNKNOWN, np.uint8)
            self.count[area] = np.zeros((f.shape[0], self.width), np.int16)
        V, C = self.val[area][:, x:x + f.shape[1]], self.count[area][:, x:x + f.shape[1]]
        return V, C, f[:, :V.shape[1]]

    def things(self, f, x, area):
        """The pixels of f that differ from settled background."""
        V, C, g = self._views(f, x, area)
        fg = np.zeros(f.shape, bool)
        fg[:, :V.shape[1]] = (g != V) & (C >= self.settle)
        return fg

    def learn(self, f, x, area, keep: np.ndarray | None = None):
        """Vote with frame f, except where `keep` (screen pixels of moving things) is set."""
        V, C, g = self._views(f, x, area)
        vote = np.ones(g.shape, bool) if keep is None else ~keep[:, :V.shape[1]]
        same, diff = vote & (g == V), vote & (g != V)
        C[same] = np.minimum(C[same] + 1, 30)
        C[diff] -= 1
        flip = vote & (C <= 0)
        V[flip], C[flip] = g[flip], 1

    def __call__(self, f, x, area):
        fg = self.things(f, x, area)
        self.learn(f, x, area)
        return fg


class Tracker:
    """Things from one frame to the next: each thing (a connected group of foreground pixels, in world
    coordinates) is matched to the nearest track predicted from its last move; unmatched things start new tracks,
    tracks unseen for a few steps end."""

    def __init__(self, reach=24, forget=6, min_px=6):
        self.reach, self.forget, self.min_px = reach, forget, min_px
        self.tracks, self.next = {}, 1
        self.mobile = set()  # kinds seen travelling: the same picture, a step apart, at different places

    def __call__(self, fg, f, x, y, t):
        things = []
        for ys, xs in components(fg):
            if len(ys) < self.min_px:
                continue
            y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
            patch = np.full((y1 - y0, x1 - x0), UNKNOWN, np.uint8)
            patch[ys - y0, xs - x0] = f[ys, xs]
            things.append({"box": [int(x0 + x), int(y0 + y), int(x1 + x), int(y1 + y)], "kind": kind_of(patch),
                           "px": int(len(ys))})
        pairs = []
        for i, th in enumerate(things):
            cx, cy = (th["box"][0] + th["box"][2]) / 2, (th["box"][1] + th["box"][3]) / 2
            for k, tr in self.tracks.items():
                px, py = tr["c"][0] + tr["v"][0], tr["c"][1] + tr["v"][1]
                d = abs(cx - px) + abs(cy - py)
                if d <= self.reach:
                    pairs.append((d, i, k))
        used_i, used_k = set(), set()
        for d, i, k in sorted(pairs):
            if i in used_i or k in used_k:
                continue
            used_i.add(i)
            used_k.add(k)
            things[i]["id"] = k
        out = []
        for i, th in enumerate(things):
            c = ((th["box"][0] + th["box"][2]) / 2, (th["box"][1] + th["box"][3]) / 2)
            k = th.get("id")
            if k is None:
                k, self.next = self.next, self.next + 1
                self.tracks[k] = {"c": c, "v": (0.0, 0.0), "seen": t, "kinds": set(), "first": c, "moved": False}
            tr = self.tracks[k]
            tr["v"] = (c[0] - tr["c"][0], c[1] - tr["c"][1]) if tr["seen"] == t - 1 else (0.0, 0.0)
            if tr["v"] != (0.0, 0.0) and tr.get("kind") == th["kind"]:
                self.mobile.add(th["kind"])
            tr["c"], tr["seen"], tr["kind"] = c, t, th["kind"]
            tr["kinds"].add(th["kind"])
            tr["moved"] = tr["moved"] or bool(tr["kinds"] & self.mobile)
            out.append(th | {"id": k, "v": [round(tr["v"][0], 1), round(tr["v"][1], 1)], "moved": tr["moved"],
                             "mobile": th["kind"] in self.mobile})
        for k in [k for k, tr in self.tracks.items() if t - tr["seen"] > self.forget]:
            del self.tracks[k]
        return out


class Sight(Module):
    """An encoder: an RGB screen to the camera's world position and the things on screen, from pixels alone.

    outputs: `camera` {x, y, area, cut}; `things` [{id, kind, box (world pixels), v (pixels a step), px, moved,
    mobile}]: `mobile` if this picture has been seen travelling (the same sprite a step apart in two places), `moved`
    if any picture on this track has (a blinking block never has; an enemy soon has). Only mobile things are kept
    out of the background vote, so a player standing still stays a thing and a patch left behind fades."""
    kind = "encoder"
    inputs = {"rgb": Port("rgb")}
    outputs = {"camera": Port("json"), "things": Port("json")}

    def __init__(self, name, crop: list | None = None, dx: list | None = None, dy: list | None = None):
        super().__init__(name)
        self.crop = crop or [0, 0]
        self.palette, self.camera = Palette(), Camera(tuple(dx or (-8, 8)), tuple(dy or (0, 0)))
        self.background, self.tracker, self.t = Background(), Tracker(), 0

    def on(self, port, msg):
        img = np.asarray(msg.data)
        top, bottom = self.crop
        f = self.palette(img[top:img.shape[0] - bottom])
        x, y, area, cut = self.camera(f)
        fg = self.background.things(f, x, area)
        things = self.tracker(fg, f, x, y + top, self.t) if not cut else []
        keep = np.zeros(f.shape, bool)
        for th in things:
            if th["mobile"]:
                x0, y0, x1, y1 = th["box"]
                keep[max(y0 - top - 2, 0):y1 - top + 2, max(x0 - x - 2, 0):x1 - x + 2] = True
        self.background.learn(f, x, area, keep)
        self.t += 1
        self.emit("camera", {"x": x, "y": y, "area": area, "cut": cut})
        self.emit("things", things)
