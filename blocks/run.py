"""The default executor (S-157, S-164): runs a plan's steps in dependency order, one block at a time.

It enforces: each block's `timeout_s` (the subprocess is killed); inputs and outputs checked against the block's
interface; one retry, only for a block that is `idempotent`; a block with `changes_world` runs only through an Env
actuator `blocks.<name>` (`Env.act`): `free` runs it, `propose` stops the run as `waiting` until the owner decides,
`deny` fails it. The `http` and `mcp` kinds are declared and refused. The run record is returned as JSON-able data;
`publish` writes it to the environment as a signal (the kernel write comes later).

    Executor(env).run(plan, inputs, catalog) -> record
    Executor(env).run(plan, inputs, catalog, resume=record)    # after the owner decided on a waiting step

`skill_gate(catalog)` is worker.run_task's `gate`: M-17's first rung (a task that matches a plan's trigger is answered
by the plan, with no model call; anything else, or a plan that fails, returns None and the model is called).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import uuid

from blocks import Block, Catalog, Invalid, refs, validate, validate_plan

BY = "blocks:executor"
BOOT = ("import importlib,json,sys;sys.path.insert(0,sys.argv[2]);m,f=sys.argv[1].split(':');"
        "print(json.dumps(getattr(importlib.import_module(m),f)(json.load(sys.stdin))))")


class StepFailed(Exception):
    pass


def invoke(block: Block, inp: dict):
    """The block run once, JSON in and out. Raises StepFailed."""
    k = block.invoke["kind"]
    if k == "python":
        argv = [sys.executable, "-I", "-c", BOOT, block.invoke["target"], str(block.root.resolve())]
    elif k == "command":
        argv = list(block.invoke["argv"])
    else:
        raise StepFailed(f"the default executor does not run {k!r} blocks yet (it runs python and command)")
    try:
        p = subprocess.run(argv, input=json.dumps(inp), capture_output=True, text=True, timeout=block.timeout_s,
                           cwd=block.root if k == "command" else None)
    except subprocess.TimeoutExpired:
        raise StepFailed(f"timeout after {block.timeout_s}s")
    except OSError as x:
        raise StepFailed(f"could not start: {x}")
    if p.returncode != 0:
        raise StepFailed(f"exit {p.returncode}: {(p.stderr or '').strip()[-300:]}")
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        raise StepFailed(f"output is not JSON: {p.stdout[:100]!r}")


class Executor:
    manifest = "blocks/executor.yaml"

    def __init__(self, env=None, by: str = BY):
        self.env, self.by = env, by

    def _attempt(self, block: Block, inp: dict) -> tuple[dict | None, str | None, int]:
        tries = 2 if block.idempotent else 1
        err = None
        for n in range(1, tries + 1):
            try:
                out = invoke(block, inp)
                validate(out, block.outputs, f"{block.name} output")
                return out, None, n
            except (StepFailed, Invalid) as x:
                err = str(x)
        return None, err, tries

    def run(self, plan: dict, inputs: dict, catalog: Catalog, resume: dict | None = None) -> dict:
        t0 = time.time()
        order = validate_plan(plan, catalog.blocks)
        steps = {s["id"]: s for s in plan["steps"]}
        variables = plan.get("variables", {})
        rec = {"run": (resume or {}).get("run") or uuid.uuid4().hex[:12], "plan": plan["name"], "version": plan["version"],
               "inputs": inputs, "steps": [], "ok": False, "status": "running", "answer": None}
        done = {r["id"]: r for r in (resume or {}).get("steps", []) if r["status"] == "ok"}
        waiting = {r["id"]: r for r in (resume or {}).get("steps", []) if r["status"] == "waiting"}
        try:
            validate(inputs, {"type": "object", "properties": variables, "required": list(variables)}, "inputs")
        except Invalid as x:
            return self._end(rec, "failed", str(x), t0)
        outputs: dict[str, dict] = {}
        for sid in order:
            s, block = steps[sid], catalog.blocks[steps[sid]["block"]]
            if sid in done:
                rec["steps"].append(done[sid])
                outputs[sid] = done[sid]["output"]
                continue
            inp = {}
            for k, src, field in refs(s):
                inp[k] = field if src is None else (inputs[field] if src == "input" else outputs[src][field])
            r = {"id": sid, "block": block.name, "input": inp, "output": None, "duration_s": 0.0, "ok": False,
                 "status": "failed", "attempts": 0, "error": None}
            rec["steps"].append(r)
            t = time.time()
            try:
                validate(inp, block.inputs, f"{block.name} input")
                if block.changes_world:
                    act = self._gate(block, rec, sid, inp, waiting.get(sid))
                    if act["status"] == "waiting":
                        r.update(status="waiting", action=act["action"], error=None)
                        return self._end(rec, "waiting", None, t0)
                    if act["status"] != "queued":
                        raise StepFailed(act["error"])
                    r["action"] = act["action"]
                out, err, n = self._attempt(block, inp)
                r["attempts"] = n
                if block.changes_world:
                    self.env.done(r["action"], out if err is None else {"error": err}, err is None)
                if err:
                    raise StepFailed(err)
            except (StepFailed, Invalid) as x:
                r.update(error=str(x), duration_s=round(time.time() - t, 3))
                return self._end(rec, "failed", f"step {sid}: {x}", t0)
            r.update(output=out, ok=True, status="ok", duration_s=round(time.time() - t, 3))
            outputs[sid] = out
        text = plan.get("answer")
        if text is not None:
            ctx = {"input": inputs, **outputs}
            text = re.sub(r"\{(\w+)\.(\w+)\}", lambda m: str(ctx[m.group(1)][m.group(2)]), text)
        rec["answer"] = text
        return self._end(rec, "ok", None, t0)

    def _gate(self, block: Block, rec: dict, sid: str, inp: dict, was_waiting: dict | None) -> dict:
        """A changes_world step through its actuator: {"status": queued | waiting | failed, action, error}."""
        if self.env is None:
            return {"status": "failed", "error": f"{block.name} changes the world and there is no environment to gate it"}
        if was_waiting:
            action, status = was_waiting["action"], self.env.status(was_waiting["action"])
        else:
            action, status = self.env.act(f"blocks.{block.name}", {"run": rec["run"], "step": sid, "input": inp}, self.by)
        if status == "proposed":
            return {"status": "waiting", "action": action}
        if status == "queued":
            return {"status": "queued", "action": action}
        return {"status": "failed", "action": action, "error": f"the gate said {status}: {block.name} was not allowed to run"}

    @staticmethod
    def _end(rec: dict, status: str, error: str | None, t0: float) -> dict:
        rec.update(status=status, ok=status == "ok", error=error, duration_s=round(time.time() - t0, 3))
        return rec

    def publish(self, rec: dict) -> None:
        """The thin optional write: the run record as a `blocks.run.done` signal."""
        self.env.publish("blocks.run.done", rec, self.by)


def skill_gate(catalog: Catalog, executor: Executor | None = None):
    """worker.run_task's `gate`. Before the first model call, a task matching a plan's trigger is run by the plan and
    its answer returned; a plan that fails or has to wait for the owner says so in the answer only when it waits.
    Otherwise None. `gate.records` keeps the run records."""
    ex = executor or Executor()
    triggers = [(re.compile(p["trigger"]["pattern"]), p) for p in catalog.plans.values() if p.get("trigger")]

    def gate(state: dict):
        if state.get("step", 0) != 0 or not isinstance(state.get("task"), str):
            return None
        for rx, plan in triggers:
            m = rx.search(state["task"])
            if not m:
                continue
            inputs, ok = {}, True
            for k, v in m.groupdict().items():
                want = plan["variables"][k]["type"]
                try:
                    inputs[k] = int(v) if want == "integer" else float(v) if want == "number" else v
                except (TypeError, ValueError):
                    ok = False
            if not ok:
                continue
            rec = ex.run(plan, inputs, catalog)
            gate.records.append(rec)
            if rec["ok"]:
                return rec["answer"] or json.dumps([s["output"] for s in rec["steps"]])
            if rec["status"] == "waiting":
                return f"Plan {plan['name']} is waiting for the owner to approve a step (run {rec['run']})."
            return None
        return None
    gate.records = []
    return gate
