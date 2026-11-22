"""One run: an environment from its declaration, an agent attached to what it exposes, taps, and a scheduler.

    python3 -m envkit.run arc3 --param game=LS20 --param seed=0 --agent atlas [--realtime --speed 4] [--film run.gif] [--live 8765]

prints the run as one line of JSON (levels or return, steps, the end event). The agent is chosen here, not in the
declaration: the environment is the world side, the agent is the candidate's (README.md, "Custody").
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from pathlib import Path

from envkit.core import Lockstep, Realtime, attach
from envkit.declare import load
from envkit.modules import PolicyAgent, Recorder


def atlas_agent(seed: int, **opts):
    from atlas.agent import Atlas

    def build(actions):
        points = actions["points"]
        return Atlas(actions["names"], lambda i: points[i], seed=seed, **opts)

    return PolicyAgent("agent", build, observe=["frame", "attempt", "levels_completed", "state"])


def mover_agent(seed: int, **opts):
    from atlas.mover import Mover
    return PolicyAgent("agent", lambda actions: Mover(actions["names"], seed=seed, **opts),
                       observe=["things", "camera", "attempt", "reward"])


def mover_ws_agent(seed: int, **opts):
    """The mover reading the workspace instead of the detectors' channels, and posting its claims back to it."""
    from atlas.mover import Mover
    from envkit.workspace import observation

    class FromWorkspace(Mover):
        def step(self, obs):
            o = observation(obs["state"])
            if "reward" not in o:  # as PolicyAgent does: wait until every reading read has arrived (no reward
                return self.names[0], None  # before the first step; the world idles the same way)
            return super().step(o)

    return PolicyAgent("agent", lambda actions: FromWorkspace(actions["names"], seed=seed, **opts),
                       observe=[], trigger="state")


def cartographer_agent(seed: int, **opts):
    from atlas.cartographer import Cartographer
    return PolicyAgent("agent", lambda actions: Cartographer(actions["names"], seed=seed, **opts),
                       observe=[], trigger="state")


AGENTS = {"atlas": atlas_agent, "mover": mover_agent, "mover_ws": mover_ws_agent, "cartographer": cartographer_agent}


def run(env_name: str, params: dict, agent: str = "atlas", profile: str | None = "judged", realtime: bool = False,
        speed: float = 1.0, agent_opts: dict | None = None, film: str | None = None, film_every: int = 2, live: int | None = None):
    env = load(env_name, **params)
    a = AGENTS[agent](int(env.params.get("seed", 0)), **(agent_opts or {}))
    attach(env, a, {p: p for p in a.inputs if p in env.expose} | {"cmd": "cmd"}
           | ({"post": "post"} if "post" in env.expose and "post" in a.outputs else {}), profile=profile)
    rec = Recorder("record", ["reward", "event"])
    attach(env, rec, {"reward": "reward", "event": "event"})
    modules = env.modules + [a, rec]
    from envkit.watch import Film, Live
    for f in ([Film("film", film, every=film_every)] if film else []) + ([Live("live", live)] if live else []):
        attach(env, f, {"screen": "screen" if "screen" in env.expose else "frame", "reward": "reward",
                        "event": "event", "tick": "tick"} | {p: p for p in ("things", "camera") if p in env.expose})
        f.wired_in["why"] = a.wired_out.get("why", f"{a.name}.why")  # a tap may read the agent too
        modules.append(f)
    t0 = time.perf_counter()
    ticks = (Realtime(modules, speed=speed).run() if realtime else Lockstep(modules).run())
    rewards = [(t, d) for t, p, d in rec.log if p == "reward" and d]
    end = next((d for t, p, d in rec.log if p == "event" and d["kind"] == "end"), None)
    lives, cur = [], 0.0  # the return of each life (a life ends at a "life" event)
    for t, p, d in rec.log:
        if p == "reward" and d:
            cur += d
        elif p == "event" and d["kind"] == "life":
            lives.append(cur)
            cur = 0.0
    lives.append(cur)
    report = a.policy.report() if hasattr(a.policy, "report") else None
    return {"env": env_name, "params": env.params, "report": report, "return": sum(d for _, d in rewards),
            "reward_ticks": [t for t, _ in rewards], "lives": lives, "end": end, "ticks": ticks,
            "seconds": round(time.perf_counter() - t0, 3)}


def main(argv=None):
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser()
    ap.add_argument("env")
    ap.add_argument("--param", action="append", default=[], help="name=value (ints are read as ints)")
    ap.add_argument("--agent", default="atlas")
    ap.add_argument("--profile", default="judged")
    ap.add_argument("--realtime", action="store_true")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--film", help="write the run as an animated GIF with the agent's reasons beside it")
    ap.add_argument("--film-every", type=int, default=2)
    ap.add_argument("--report", help="write the agent's report (if it has one) to this file")
    ap.add_argument("--live", type=int, metavar="PORT", help="serve the run as it happens on 127.0.0.1:PORT")
    a = ap.parse_args(argv)
    params = {}
    for kv in a.param:
        k, _, v = kv.partition("=")
        params[k] = int(v) if v.lstrip("-").isdigit() else v
    out = run(a.env, params, a.agent, a.profile or None, a.realtime, a.speed,
                         film=a.film, film_every=a.film_every, live=a.live)
    report = out.pop("report", None)
    if a.report and report:
        Path(a.report).write_text(report)
    print(json.dumps(out))


if __name__ == "__main__":
    sys.exit(main())
