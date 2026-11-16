"""The step loop (README.md, "Episodes"): an environment's observation, the route asked at this step, the action
its answer gives, the environment's `step`, until the episode ends. One function, called the same way by a judged
run's driver and by the plugin's `run` extractor, so a benchmark and a live input look alike to the handlers.

The environment is any object with Gymnasium's two calls (MIT, unchanged):

    reset(case: dict, seed: int) -> observation
    step(action: dict) -> (observation, reward, terminated, truncated, info)

and `final()`, the state the outcome is read from. An observation is a list of claims (dicts with subject,
property, value, source, time). The handler contract (ladder.py) does not change: each step, every handler on the
route gets one item,

    {"observation": the claims new at this step, "episode": the steps before it, in order, "step": its number,
     "actions": the environment's action kinds and their arguments, if it lists them}

and the action is the `value` of the first answer on the route. Each earlier step is {"observation", "action",
"by"}, whoever took it, so a model handler can show the episode as a log that only grows (its context filler).

Two actions are the loop's, not the environment's (docs: "How it grows"): `ask` hands this step to another
handler that exists, recorded as a nested call; the asked handler's answer is the action. An unknown handler
leaves the action as given, and the environment refuses it. Everything else goes to `step` as it is.

An escalation that leaves the top of the route ends the episode as `escalated`; so does an action the
environment says hands the work up (`info["escalated"]`). Nothing here imports the store.
"""
from __future__ import annotations

import ladder
from ladder import Call, Runner


def run(env, case: dict, order: list[str], entries: dict[str, str], *, seed: int = 0, max_steps: int = 30,
        reveal: set | None = None) -> dict:
    """One episode. Returns {"end": terminated|truncated|escalated, "steps", "final", "actions", "log", "calls"};
    `log` is every step's observation, action and handler, `calls` every handler call made, in order."""
    observation = env.reset(case, seed)
    actions = env.actions() if hasattr(env, "actions") else None     # the action kinds, for a handler to offer
    log: list[dict] = []
    calls: list[Call] = []
    end = None
    while end is None:
        item = {"observation": observation, "episode": [dict(s) for s in log], "step": len(log) + 1, "actions": actions}
        runner = Runner(order, entries, "final", reveal=reveal or set())
        made = runner.handle(item)
        top = next((c for c in made if c.kind == "answer" and c.parent is None), None)
        if top is not None and isinstance(top.value, dict) and top.value.get("kind") == "ask":
            asked = top.value.get("handler")
            if asked in entries:
                nested = Runner([asked], entries, "final", reveal=reveal or set()).handle(item)
                got = next((c for c in nested if c.kind == "answer" and c.parent is None), None)
                base, asker = len(made), made.index(top)
                for c in nested:           # recorded as calls the asking handler made
                    c.parent = asker if c.parent is None else c.parent + base
                made += nested
                top = got if got is not None else top
        calls += made
        if top is None:
            log.append({"observation": observation, "action": None, "by": None})
            end = "escalated"
            break
        action = top.value if isinstance(top.value, dict) else {"kind": None, "value": top.value}
        log.append({"observation": observation, "action": action, "by": top.handler})
        observation, _reward, terminated, truncated, info = env.step(action)
        if (info or {}).get("escalated"):
            end = "escalated"
        elif terminated:
            end = "terminated"
        elif truncated or len(log) >= max_steps:
            end = "truncated"
    return {"end": end, "steps": len(log), "final": env.final(), "actions": [s["action"] for s in log if s["action"]],
            "log": log, "last": observation if log and log[-1]["action"] else None, "calls": calls}


def load(path, name: str):
    """A module from a file, under a name of the caller's choosing (a package's environment or handler)."""
    import importlib.util
    import sys
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def route(directory, agent: dict, model: str | None, gateway, prefix: str = "") -> tuple[list[str], dict[str, str]]:
    """The route an agent file describes (docs: `agent.yaml`), cheapest first by its kinds' priors (`select:
    cost-order`, the one filler built). A handler whose entry is a .py file in the directory is made by that file's
    `make(slug, cfg, gateway, directory)`, with `cfg` its line, the agent's parameters and the environment's model;
    any other entry is a name already registered with the runner."""
    from pathlib import Path
    from ladder import PRIOR, rank_key
    directory = Path(directory)
    if (agent.get("select") or "cost-order") != "cost-order":
        raise ValueError(f"select {agent.get('select')!r}: only cost-order is built")
    entries, kinds = {}, {}
    for name, h in (agent.get("handlers") or {}).items():
        slug, entry = prefix + name, str(h.get("entry") or name)
        kinds[slug] = h.get("kind", "script")
        if entry.endswith(".py"):
            module = load(directory / entry, f"agent_{slug.replace('-', '_')}_{Path(entry).stem}")
            module.make(slug, {**h, "model": model or h.get("model"), "parameters": agent.get("parameters") or h.get("parameters") or {}},
                        gateway, directory)
            entries[slug] = slug
        else:
            entries[slug] = entry
    order = sorted(entries, key=lambda s: (rank_key(PRIOR.get(kinds[s], PRIOR["script"])), s))
    return order, entries
