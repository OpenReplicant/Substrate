"""Run one candidate on one case; print one JSON line. argv: candidate case base_url mcp_python mcp_script
case "tool": task -> tool call -> tool result -> final answer.
case "veto": our gate refuses the 2nd model call (the one after the tool result); expect the answer to be withheld."""
import asyncio, importlib, json, sys, time

cand, case, base, mcp_py, mcp_script = sys.argv[1:6]


class Vetoed(Exception):
    pass


n = {"asked": 0}


def gate():
    n["asked"] += 1
    if case == "veto" and n["asked"] == 2:
        raise Vetoed()


mod = importlib.import_module("agent_" + cand)
t = time.time()
out = {"candidate": cand, "case": case}
try:
    ans = asyncio.run(mod.run("What is 2 + 3? Use the add tool.", base, "stub-key", [mcp_py, mcp_script], gate))
    out.update(result=ans, error=None)
except BaseException as e:  # frameworks wrap exceptions in groups; look for Vetoed anywhere
    chain, seen = [e], set()
    while chain:
        x = chain.pop()
        if id(x) in seen:
            continue
        seen.add(id(x))
        if isinstance(x, Vetoed):
            out.update(result=None, error="Vetoed")
            break
        chain += [y for y in (x.__cause__, x.__context__, *getattr(x, "exceptions", ())) if y]
    else:
        out.update(result=None, error=repr(e)[:200])
out.update(gate_asked=n["asked"], secs=round(time.time() - t, 2))
time.sleep(0.5)
print(json.dumps(out))
