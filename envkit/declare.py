"""Environments from declarations: a TOML file of data, no code (README.md).

    [environment]  name, doc
    [params]       defaults, each overridable when the environment is loaded; "{name}" in any string below is
                   replaced by its value (a whole-string "{name}" keeps the value's type)
    [[module]]     name, driver (a key of modules.DRIVERS) or env (another declaration, nested), the driver's
                   own arguments, and `wire` (port -> "module.port": the channel an input reads or an output writes)
    [expose]       exposed name -> "module.port"
    [profiles]     profile -> the exposed readings fair under it

A parameter whose value is "$NAME" is read from the machine's environment variable NAME (a ROM's path, say), so
nothing private is written in a declaration.
"""
from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path

from envkit.core import Environment, nest
from envkit.modules import DRIVERS

ROOT = Path(__file__).resolve().parent / "declarations"


def _fill(v, params):
    if isinstance(v, str):
        whole = re.fullmatch(r"\{(\w+)\}", v)
        if whole:
            return params[whole.group(1)]
        return re.sub(r"\{(\w+)\}", lambda m: str(params[m.group(1)]), v)
    if isinstance(v, dict):
        return {k: _fill(x, params) for k, x in v.items()}
    if isinstance(v, list):
        return [_fill(x, params) for x in v]
    return v


def find(name: str) -> Path:
    p = Path(name)
    return p if p.suffix == ".toml" and p.exists() else ROOT / f"{name}.toml"


def load(name: str, **overrides) -> Environment:
    d = tomllib.loads(find(name).read_text())
    params = dict(d.get("params", {}))
    unknown = set(overrides) - set(params)
    if unknown:
        raise KeyError(f"{name} has no parameters {sorted(unknown)}")
    params.update(overrides)
    for k, v in params.items():
        if isinstance(v, str) and v.startswith("$"):
            params[k] = os.environ.get(v[1:], "")
    modules = []
    for spec in d.get("module", []):
        spec = _fill(dict(spec), params)
        mname = spec.pop("name")
        if "env" in spec:  # a nested environment: its modules join under this name, its exposed names with them
            child = load(spec.pop("env"), **spec.pop("params", {}))
            modules += nest(mname, child)
            continue
        wire = spec.pop("wire", {})
        m = DRIVERS[spec.pop("driver")](mname, **spec)
        for port, ch in wire.items():
            if port in m.inputs:
                m.wired_in[port] = ch
            elif port in m.outputs:
                m.wired_out[port] = ch
            else:
                raise KeyError(f"{mname} has no port {port!r}")
        modules.append(m)
    env = Environment(d["environment"]["name"], modules, expose=d.get("expose", {}),
                      profiles=d.get("profiles", {}), doc=d["environment"].get("doc", ""))
    env.params = params
    return env
