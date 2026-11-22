"""Blocks, plans, the default executor and the skill gate (plan step 3, S-164). No database, no network: a fake Env stands
in for env.act, and the worker's loop runs with a model stub.
It should:
- accept the example blocks and plan, and refuse bad blocks (missing field, bad schema, unknown kind, bad effects)
- refuse bad plans: a missing block, a type mismatch, an unmapped required input, a cycle
- run steps in dependency order, validate inputs and outputs, and keep a run record (input, output, duration, ok)
- enforce the timeout, retry only idempotent blocks once, refuse the http and mcp kinds
- send a changes_world block through an actuator: it waits when proposed, runs once approved, fails when denied
- answer a matching task through worker.run_task without a model call (skipped_calls 1, model_calls 0); return None otherwise

    python3 scripts/tests/test_blocks.py
"""
import asyncio
import copy
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import blocks as B  # noqa: E402
from blocks import run as R  # noqa: E402
from environment import worker as w  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print(("ok  " if ok else "FAIL"), name, "" if ok else detail)


def raises(fn):
    try:
        fn()
    except B.Invalid:
        return True
    return False


class FakeEnv:
    """env.act, status, done and publish in memory. `gate` is what the actuator answers on the first call."""
    def __init__(self, gate="queued"):
        self.gate, self.actions, self.published = gate, {}, []

    def act(self, actuator, input_, by):
        i = len(self.actions) + 1
        self.actions[i] = {"actuator": actuator, "input": input_, "status": self.gate, "done": None}
        return i, self.gate

    def status(self, i):
        return self.actions[i]["status"]

    def done(self, i, result, ok=True):
        self.actions[i]["done"] = (result, ok)

    def publish(self, key, body, by, headers=None):
        self.published.append(key)
        return 1


def block(name, code, **eff):
    """A python block in a temp directory: input {"x": integer}, output {"y": integer}."""
    d = Path(tempfile.mkdtemp()) / name
    d.mkdir()
    (d / f"{name}.py").write_text(code)
    spec = {"name": name, "version": "1", "description": name,
            "interface": {"inputs": {"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"]},
                          "outputs": {"type": "object", "properties": {"y": {"type": "integer"}}, "required": ["y"]}},
            "effects": {"changes_world": False, "idempotent": True, "timeout_s": 5, **eff},
            "invoke": {"kind": "python", "target": f"{name}:run"}}
    return B.validate_block(spec, d)


def plan(steps, **kw):
    return {"type": "Plan", "name": "p", "version": "1", "variables": {"n": {"type": "integer"}}, "steps": steps, **kw}


def cat(*bs, plans=()):
    return B.Catalog({b.name: b for b in bs}, {p["name"]: p for p in plans})


def main():
    ex_dir = ROOT / "blocks" / "examples"
    catalog = B.load_catalog(ex_dir)
    check("the example blocks and plan load and validate", set(catalog.blocks) == {"word_count", "write_note"}
          and set(catalog.plans) == {"note_with_count"}, catalog.blocks)
    check("the executor's manifest is in the catalog as a code-layer executor", "layer: code" in (ROOT / "blocks/executor.yaml").read_text())

    # blocks: good and bad
    good = json.loads(json.dumps(B.load_block(ex_dir / "word_count").spec))
    for what, edit in {
        "a missing field": lambda s: s.pop("effects"),
        "a bad schema type": lambda s: s["interface"]["inputs"]["properties"]["text"].update(type="str"),
        "a schema keyword outside the subset": lambda s: s["interface"]["inputs"].update(pattern="x"),
        "an unknown invoke kind": lambda s: s["invoke"].update(kind="grpc"),
        "a python target without a function": lambda s: s["invoke"].update(target="word_count"),
        "effects that are not booleans": lambda s: s["effects"].update(idempotent="yes"),
        "a zero timeout": lambda s: s["effects"].update(timeout_s=0),
        "a required name that is not declared": lambda s: s["interface"]["inputs"].update(required=["nope"]),
    }.items():
        s = copy.deepcopy(good)
        edit(s)
        check(f"a block with {what} is refused", raises(lambda: B.validate_block(s)))
    check("the schema subset validates values", raises(lambda: B.validate({"words": "x"}, good["interface"]["outputs"]))
          and not raises(lambda: B.validate({"words": 3}, good["interface"]["outputs"])))

    # plans
    a, b = block("a", "def run(i): return {'y': i['x'] + 1}"), block("b", "def run(i): return {'y': i['x'] * 10}")
    c = cat(a, b)
    s1 = {"id": "s1", "block": "a", "inputs": {"x": "$input.n"}}
    s2 = {"id": "s2", "block": "b", "inputs": {"x": "$s1.y"}}
    check("a good plan validates; order follows dependencies, not listing", B.validate_plan(plan([s2, s1]), c.blocks) == ["s1", "s2"])
    check("a plan naming a missing block is refused", raises(lambda: B.validate_plan(plan([{"id": "s", "block": "zzz", "inputs": {}}]), c.blocks)))
    check("a type mismatch is refused", raises(lambda: B.validate_plan(
        {**plan([s1]), "variables": {"n": {"type": "string"}}}, c.blocks)))
    check("an unmapped required input is refused", raises(lambda: B.validate_plan(plan([{"id": "s", "block": "a", "inputs": {}}]), c.blocks)))
    check("a reference to an unknown step is refused", raises(lambda: B.validate_plan(
        plan([{"id": "s", "block": "a", "inputs": {"x": "$ghost.y"}}]), c.blocks)))
    cyc1 = {"id": "c1", "block": "a", "inputs": {"x": "$c2.y"}}
    cyc2 = {"id": "c2", "block": "b", "inputs": {"x": "$c1.y"}}
    check("a cycle is refused", raises(lambda: B.validate_plan(plan([cyc1, cyc2]), c.blocks)))
    check("a trigger group that is not a plan variable is refused", raises(lambda: B.validate_plan(
        plan([s1], trigger={"pattern": "(?P<zzz>\\d+)"}), c.blocks)))

    # the executor
    ex = R.Executor()
    r = ex.run(plan([s2, s1], answer="{s2.y}"), {"n": 4}, c)
    check("steps run in dependency order and the answer uses their outputs", r["ok"] and [s["id"] for s in r["steps"]] == ["s1", "s2"]
          and r["answer"] == "50", r)
    check("the run record keeps each step's input, output, duration and ok",
          all({"input", "output", "duration_s", "ok"} <= set(s) for s in r["steps"]) and r["steps"][1]["input"] == {"x": 5}
          and json.loads(json.dumps(r)) == r, r)
    check("inputs that do not fit the plan's variables fail the run before any step", ex.run(plan([s1]), {"n": "x"}, c)["status"] == "failed")

    slow = block("slow", "import time\ndef run(i):\n    time.sleep(3)\n    return {'y': 1}", timeout_s=0.5, idempotent=False)
    r = ex.run(plan([{"id": "s", "block": "slow", "inputs": {"x": "$input.n"}}]), {"n": 1}, cat(slow))
    check("a block over its timeout is killed and the run fails", r["status"] == "failed" and "timeout" in r["steps"][0]["error"]
          and r["steps"][0]["duration_s"] < 2, r)

    flaky_code = ("import os, sys\ndef run(i):\n    p = os.environ['MARK']\n    n = int(open(p).read()) if os.path.exists(p) else 0\n"
                  "    open(p, 'w').write(str(n + 1))\n    if n < int(os.environ['FAILS']): raise RuntimeError('boom')\n    return {'y': n}\n")
    mark = tempfile.mktemp()
    os.environ["MARK"] = mark
    fs = {"id": "f", "block": "flaky", "inputs": {"x": "$input.n"}}
    os.environ["FAILS"] = "1"
    flaky = block("flaky", flaky_code, idempotent=True)
    r = ex.run(plan([fs]), {"n": 1}, cat(flaky))
    check("an idempotent block is retried once and then succeeds", r["ok"] and r["steps"][0]["attempts"] == 2, r)
    os.remove(mark)
    os.environ["FAILS"] = "5"
    r = ex.run(plan([fs]), {"n": 1}, cat(flaky))
    check("an idempotent block that keeps failing is tried twice only", not r["ok"] and r["steps"][0]["attempts"] == 2
          and open(mark).read() == "2", r)
    os.remove(mark)
    once = block("flaky", flaky_code, idempotent=False)
    r = ex.run(plan([fs]), {"n": 1}, cat(once))
    check("a block that is not idempotent is never retried", not r["ok"] and r["steps"][0]["attempts"] == 1 and open(mark).read() == "1", r)

    bad = block("badout", "def run(i): return {'y': 'text'}")
    r = ex.run(plan([{"id": "s", "block": "badout", "inputs": {"x": "$input.n"}}]), {"n": 1}, cat(bad))
    check("an output that breaks the block's interface fails the step", r["status"] == "failed" and "expected integer" in r["steps"][0]["error"], r)

    http = copy.deepcopy(a.spec)
    http.update(name="remote", invoke={"kind": "http", "url": "https://example.invalid"})
    rb = B.validate_block(http)
    r = ex.run(plan([{"id": "s", "block": "remote", "inputs": {"x": "$input.n"}}]), {"n": 1}, cat(rb))
    check("http and mcp are declared kinds the executor refuses, clearly", r["status"] == "failed" and "does not run 'http'" in r["steps"][0]["error"], r)

    cmd = copy.deepcopy(a.spec)
    cmd.update(name="viacmd", invoke={"kind": "command", "argv": [sys.executable, "-I", "-c",
               "import json,sys;print(json.dumps({'y': json.load(sys.stdin)['x'] + 100}))"]})
    r = ex.run(plan([{"id": "s", "block": "viacmd", "inputs": {"x": "$input.n"}}], answer="{s.y}"), {"n": 1}, cat(B.validate_block(cmd)))
    check("a command block takes JSON on stdin and gives JSON on stdout", r["ok"] and r["answer"] == "101", r)

    # changes_world through the gate
    ws = tempfile.mkdtemp()
    os.environ["WORKER_WORKSPACE"] = ws
    w1 = {"id": "w", "block": "writer", "inputs": {"x": "$input.n"}}
    writer_code = ("import os\ndef run(i):\n    open(os.path.join(os.environ['WORKER_WORKSPACE'], 'out.txt'), 'a').write('x')\n"
                   "    return {'y': i['x']}\n")
    writer = block("writer", writer_code, changes_world=True)
    r = ex.run(plan([w1]), {"n": 1}, cat(writer))
    check("a changes_world block with no environment is refused, not run", r["status"] == "failed" and not os.path.exists(ws + "/out.txt"), r)
    env = FakeEnv("proposed")
    r = R.Executor(env).run(plan([s1, w1]), {"n": 1}, cat(a, writer))
    check("proposed: the run waits, the block did not run, the earlier step did",
          r["status"] == "waiting" and r["steps"][0]["ok"] and r["steps"][1]["status"] == "waiting" and not os.path.exists(ws + "/out.txt")
          and env.actions[1]["actuator"] == "blocks.writer", r)
    r2 = R.Executor(env).run(plan([s1, w1]), {"n": 1}, cat(a, writer), resume=r)
    check("still proposed on resume: still waiting, and no second proposal", r2["status"] == "waiting" and len(env.actions) == 1, r2)
    env.actions[1]["status"] = "queued"
    r3 = R.Executor(env).run(plan([s1, w1]), {"n": 1}, cat(a, writer), resume=r2)
    check("approved: resume runs the block once, reuses the first step, and closes the action", r3["ok"] and r3["run"] == r["run"]
          and open(ws + "/out.txt").read() == "x" and env.actions[1]["done"] == ({"y": 1}, True), r3)
    env = FakeEnv("queued")
    r = R.Executor(env).run(plan([w1]), {"n": 1}, cat(writer))
    check("a free gate runs it at once, through the actuator", r["ok"] and len(env.actions) == 1 and env.actions[1]["done"][1], r)
    env = FakeEnv("denied")
    n0 = open(ws + "/out.txt").read()
    r = R.Executor(env).run(plan([w1]), {"n": 1}, cat(writer))
    check("denied: the block does not run and the run fails", r["status"] == "failed" and open(ws + "/out.txt").read() == n0, r)
    R.Executor(env).publish(r)
    check("the run record can be published as a signal", env.published == ["blocks.run.done"])

    # the skill gate, in the worker's loop
    async def refuses(messages, specs):
        raise AssertionError("the model was called")

    tools = w.Tools(ws)
    gate = R.skill_gate(catalog, R.Executor(FakeEnv("queued")))
    out = asyncio.run(w.run_task("Save a note called todo: buy more tea please", refuses, tools, gate=gate))
    check("a matching task is answered by the plan with no model call", out["ok"] and out["model_calls"] == 0 and out["skipped_calls"] == 1
          and out["text"] == "Saved notes/todo.txt (4 words)." and open(ws + "/notes/todo.txt").read() == "buy more tea please", out)

    async def says(messages, specs):
        return {"content": "model answer", "tool_calls": []}
    gate = R.skill_gate(catalog, R.Executor(FakeEnv("queued")))
    out = asyncio.run(w.run_task("what is the weather", says, tools, gate=gate))
    check("a task that matches nothing returns None and the model answers", out["text"] == "model answer" and out["model_calls"] == 1
          and out["skipped_calls"] == 0 and gate({"task": "hello", "step": 0}) is None, out)
    out = asyncio.run(w.run_task("Save a note called todo: x", says, tools, gate=R.skill_gate(catalog)))
    check("a plan that cannot run (no environment for its gated block) leaves the task to the model", out["model_calls"] == 1, out)
    out = asyncio.run(w.run_task("Save a note called ../x: hi", says, tools, gate=R.skill_gate(catalog, R.Executor(FakeEnv()))))
    check("the trigger's pattern does not match a name with a slash", out["model_calls"] == 1, out)
    gate = R.skill_gate(catalog, R.Executor(FakeEnv("proposed")))
    out = asyncio.run(w.run_task("Save a note called t2: hello there", refuses, tools, gate=gate))
    check("a gated step proposed: the task is answered with the waiting notice, still no model call",
          out["skipped_calls"] == 1 and "waiting for the owner" in out["text"], out)

    print(f"{sum(checks)}/{len(checks)} checks")
    sys.exit(0 if all(checks) else 1)


if __name__ == "__main__":
    main()
