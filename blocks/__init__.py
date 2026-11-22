"""Blocks and assemblies (S-157, S-164): what an agent compiles from what it solved, as catalog entries that run without the model.

A block is a directory with `block.yaml` (or `block.json`) and its code:

    name, version, description
    interface:  {inputs, outputs}   JSON Schema, kept to the subset below: the shape of a WoT Thing Description
                                    action's `input` and `output` data schemas
    effects:    {changes_world, idempotent, timeout_s}
    invoke:     {kind: python, target: "module:function"}   run in a subprocess, `python -I`, JSON in on stdin, JSON out
                {kind: command, argv: [...]}                JSON on stdin, JSON on stdout
                {kind: http | mcp}                          declared kinds; the default executor refuses them

Schema subset: type (object, array, string, number, integer, boolean, null), properties, required, items, enum.

A plan (an assembly) is JSON, data and not code; in the kernel it is a PROV-O plan (`prov:Plan`; a run is a
`prov:Activity` that `prov:hadPlan` it) with the vocabulary profile's own terms for steps, order and variables (S-175,
the kernel's D-124; P-Plan was dropped for its non-commercial licence):

    {"type": "Plan", "name", "version", "description",
     "variables": {"text": {"type": "string"}},                 the plan's inputs (its variables)
     "steps": [{"id": "count", "block": "word_count",           a step: the block it runs
                "inputs": {"text": "$input.text"}}],            "$input.x" a variable, "$step.field" an earlier
                                                                step's output, {"value": ...} a literal
     "answer": "{count.words} words",                           what the plan says when it is done
     "trigger": {"pattern": "(?i)^count (?P<text>.+)$"}}        optional: a task that matches runs it (the skill gate)

A step precedes another when the second reads its output ; order follows from that.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

TYPES = {"object", "array", "string", "number", "integer", "boolean", "null"}
KINDS = {"python", "command", "http", "mcp"}


class Invalid(ValueError):
    """A block or plan that does not hold together."""


# ---- the schema subset

def check_schema(s, path="schema") -> None:
    if not isinstance(s, dict) or s.get("type") not in TYPES:
        raise Invalid(f"{path}: needs a `type` of {sorted(TYPES)}")
    for k in s:
        if k not in {"type", "properties", "required", "items", "enum", "description", "title"}:
            raise Invalid(f"{path}: {k!r} is outside the supported subset")
    for k, v in (s.get("properties") or {}).items():
        check_schema(v, f"{path}.{k}")
    if "items" in s:
        check_schema(s["items"], f"{path}[]")
    if not set(s.get("required", [])) <= set(s.get("properties", {})):
        raise Invalid(f"{path}: `required` names a property that is not declared")


def validate(value, s, path="value") -> None:
    """Raise Invalid when `value` does not fit schema `s` (the subset above)."""
    t = s["type"]
    ok = {"object": isinstance(value, dict), "array": isinstance(value, list), "string": isinstance(value, str),
          "boolean": isinstance(value, bool), "null": value is None,
          "integer": isinstance(value, int) and not isinstance(value, bool),
          "number": isinstance(value, (int, float)) and not isinstance(value, bool)}[t]
    if not ok:
        raise Invalid(f"{path}: expected {t}, got {type(value).__name__}")
    if "enum" in s and value not in s["enum"]:
        raise Invalid(f"{path}: not one of {s['enum']}")
    if t == "object":
        for k in s.get("required", []):
            if k not in value:
                raise Invalid(f"{path}: missing {k!r}")
        for k, v in value.items():
            if k in s.get("properties", {}):
                validate(v, s["properties"][k], f"{path}.{k}")
    if t == "array" and "items" in s:
        for i, v in enumerate(value):
            validate(v, s["items"], f"{path}[{i}]")


def assignable(src: dict, dst: dict) -> bool:
    return src["type"] == dst["type"] or (src["type"] == "integer" and dst["type"] == "number")


# ---- blocks

class Block:
    def __init__(self, spec: dict, root: Path):
        self.spec, self.root = spec, Path(root)
        self.name, self.version = spec["name"], spec["version"]
        self.inputs, self.outputs = spec["interface"]["inputs"], spec["interface"]["outputs"]
        e = spec["effects"]
        self.changes_world, self.idempotent, self.timeout_s = e["changes_world"], e["idempotent"], e["timeout_s"]
        self.invoke = spec["invoke"]

    def __repr__(self):
        return f"Block({self.name} {self.version})"


def load_block(directory) -> Block:
    d = Path(directory)
    f = next((d / n for n in ("block.yaml", "block.json") if (d / n).is_file()), None)
    if f is None:
        raise Invalid(f"{d}: no block.yaml or block.json")
    if f.suffix == ".yaml":
        import yaml                                   # PyYAML 6.0.3, pinned in deploy/tools
        spec = yaml.safe_load(f.read_text())
    else:
        spec = json.loads(f.read_text())
    return validate_block(spec, d)


def validate_block(spec, root=".") -> Block:
    if not isinstance(spec, dict):
        raise Invalid("a block is a mapping")
    for k in ("name", "version", "description", "interface", "effects", "invoke"):
        if k not in spec:
            raise Invalid(f"missing {k!r}")
    if not re.fullmatch(r"[a-z][a-z0-9_]*", str(spec["name"])):
        raise Invalid("name: lowercase letters, digits and _")
    i = spec["interface"]
    if not isinstance(i, dict) or "inputs" not in i or "outputs" not in i:
        raise Invalid("interface needs inputs and outputs")
    for k in ("inputs", "outputs"):
        check_schema(i[k], f"interface.{k}")
        if i[k]["type"] != "object":
            raise Invalid(f"interface.{k}: must be an object schema")
    e = spec["effects"]
    if not (isinstance(e, dict) and isinstance(e.get("changes_world"), bool) and isinstance(e.get("idempotent"), bool)
            and isinstance(e.get("timeout_s"), (int, float)) and not isinstance(e.get("timeout_s"), bool) and e["timeout_s"] > 0):
        raise Invalid("effects: changes_world (bool), idempotent (bool), timeout_s (> 0)")
    v = spec["invoke"]
    if not isinstance(v, dict) or v.get("kind") not in KINDS:
        raise Invalid(f"invoke.kind: one of {sorted(KINDS)}")
    if v["kind"] == "python" and not re.fullmatch(r"[A-Za-z_][\w.]*:[A-Za-z_]\w*", str(v.get("target", ""))):
        raise Invalid("invoke.target: module:function")
    if v["kind"] == "command" and not (isinstance(v.get("argv"), list) and v["argv"] and all(isinstance(a, str) for a in v["argv"])):
        raise Invalid("invoke.argv: a non-empty list of strings")
    return Block(spec, root)


# ---- plans

REF = re.compile(r"\$([A-Za-z_]\w*)\.([A-Za-z_]\w*)$")


def refs(step: dict):
    """(input name, source, field) for each mapped input; source is 'input' or a step id; literals give None."""
    for k, v in step.get("inputs", {}).items():
        if isinstance(v, str):
            m = REF.match(v)
            if not m:
                raise Invalid(f"step {step['id']}: {k}: {v!r} is not a $reference (use {{\"value\": ...}} for a literal)")
            yield k, m.group(1), m.group(2)
        elif isinstance(v, dict) and set(v) == {"value"}:
            yield k, None, v["value"]
        else:
            raise Invalid(f"step {step['id']}: {k}: a $reference or {{\"value\": ...}}")


def validate_plan(plan: dict, blocks: dict) -> list[str]:
    """Raise Invalid if the plan does not hold together; return the step ids in an order that respects dependencies."""
    if not isinstance(plan, dict) or plan.get("type") != "Plan":
        raise Invalid('a plan has "type": "Plan"')
    for k in ("name", "version", "steps"):
        if k not in plan:
            raise Invalid(f"plan: missing {k!r}")
    variables = plan.get("variables", {})
    for k, s in variables.items():
        check_schema(s, f"variables.{k}")
    steps = {}
    for s in plan["steps"]:
        if s.get("id") in steps or not isinstance(s.get("id"), str) or s["id"] == "input":
            raise Invalid(f"step id {s.get('id')!r} is missing, reused or reserved")
        steps[s["id"]] = s
    deps: dict[str, set[str]] = {}
    for sid, s in steps.items():
        b = blocks.get(s.get("block"))
        if b is None:
            raise Invalid(f"step {sid}: no block {s.get('block')!r} in the catalog")
        deps[sid] = set()
        mapped = set()
        for k, src, field in refs(s):
            if k not in b.inputs.get("properties", {}):
                raise Invalid(f"step {sid}: block {b.name} has no input {k!r}")
            mapped.add(k)
            want = b.inputs["properties"][k]
            if src is None:
                validate(field, want, f"step {sid}.{k}")
                continue
            if src == "input":
                have = variables.get(field)
            elif src in steps:
                deps[sid].add(src)
                ob = blocks.get(steps[src].get("block"))
                have = ob.outputs.get("properties", {}).get(field) if ob else None
            else:
                raise Invalid(f"step {sid}: {k}: no step or variable source {src!r}")
            if have is None:
                raise Invalid(f"step {sid}: {k}: {src}.{field} is not declared")
            if not assignable(have, want):
                raise Invalid(f"step {sid}: {k}: {src}.{field} is {have['type']}, the block wants {want['type']}")
        missing = set(b.inputs.get("required", [])) - mapped
        if missing:
            raise Invalid(f"step {sid}: required inputs not mapped: {sorted(missing)}")
    order: list[str] = []
    left = dict(deps)
    while left:
        ready = [s for s in steps if s in left and not (left[s] - set(order))]
        if not ready:
            raise Invalid(f"cycle among steps {sorted(left)}")
        order.append(ready[0])
        del left[ready[0]]
    trig = plan.get("trigger")
    if trig:
        try:
            rx = re.compile(trig["pattern"])
        except (re.error, KeyError, TypeError) as x:
            raise Invalid(f"trigger.pattern: {x}")
        for g in rx.groupindex:
            if g not in variables:
                raise Invalid(f"trigger group {g!r} is not a plan variable")
    for m in re.finditer(r"\{(\w+)\.(\w+)\}", plan.get("answer", "")):
        src, field = m.groups()
        if not ((src == "input" and field in variables) or (src in steps and field in blocks[steps[src]["block"]].outputs.get("properties", {}))):
            raise Invalid(f"answer: {{{src}.{field}}} is not declared")
    return order


# ---- the catalog: blocks and plans found under a directory

class Catalog:
    def __init__(self, blocks: dict, plans: dict):
        self.blocks, self.plans = blocks, plans


def load_catalog(root) -> Catalog:
    root = Path(root)
    blocks = {}
    for f in sorted(list(root.glob("*/block.yaml")) + list(root.glob("*/block.json"))):
        b = load_block(f.parent)
        blocks[b.name] = b
    plans = {}
    for f in sorted(root.glob("plans/*.json")):
        p = json.loads(f.read_text())
        validate_plan(p, blocks)
        plans[p["name"]] = p
    return Catalog(blocks, plans)
