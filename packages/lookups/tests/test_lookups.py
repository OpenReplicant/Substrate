"""The lookups package without a model or the network: the environment's actions and replay, the model handler's
log (append-only, cut to its window) against a fake gateway, and the driver and scorer end to end on fixture cases.
The dev cases are not read here (scripts/contract.sh environment lookups checks them).

    python3 packages/lookups/tests/test_lookups.py
"""
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(HERE), str(HERE.parents[1] / "plugins/handlers")]

import driver  # noqa: E402
import environment as E  # noqa: E402
import score  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print(("ok  " if ok else "FAIL"), name, "" if ok else detail)


PAGE = {"info": {"license": "MIT", "license_expression": None, "version": "1.2.0", "description": "x" * 500,
                 **{f"field_{i}": "a value of some length" for i in range(30)}},
        "releases": {f"0.{i}": [] for i in range(100)}, "urls": [{"upload_time_iso_8601": "2026-01-02T00:00:00Z"}]}
record = E.Record()
record.entries["https://pypi.org/pypi/demo/json"] = {"url": "https://pypi.org/pypi/demo/json", "read_at": "2026-11-15T00:00:00Z",
                                                     "sha256": "0", "status": 200, "body": json.dumps(PAGE)}
CASES = [{"id": "f-1", "question": "What licence does PyPI list for the Python package demo?", "registry": "pypi", "name": "demo"},
         {"id": "f-2", "question": "What is the latest version of demo on PyPI?", "registry": "pypi", "name": "demo"}]
GOLD = {"f-1": "MIT", "f-2": "1.2.0"}

env = E.make(record)
first = env.reset(CASES[0], 0)
check("the first observation is the question alone", [c["property"] for c in first] == ["question"], first)
obs, reward, term, trunc, _ = env.step({"kind": "fetch", "url": "https://pypi.org/project/demo/"})
props = {c["property"]: c["value"] for c in obs}
check("a registry's web page is read as its JSON page, and shown as path = value claims",
      props.get("info/license") == "MIT" and reward is None and not term, list(props)[:8])
check("a long string is cut and a long object shown as its size", props["info/description"].endswith("…") and
      props["releases"].startswith("{100 fields"), (props["info/description"][-5:], props["releases"]))
obs = env.step({"kind": "fetch", "url": "https://pypi.org/pypi/demo/json", "path": "urls/0"})[0]
check("a path reads the fields under it", obs[0]["property"] == "urls/0/upload_time_iso_8601", obs)
obs = env.step({"kind": "fetch", "url": "https://pypi.org/pypi/other/json"})[0]
check("a page not in the record is an observation saying so, not a network call", obs[0]["property"] == "not recorded", obs)
obs = env.step({"kind": "fetch", "url": "https://example.com/x"})[0]
check("a page off the registries is refused", obs[0]["property"] == "refused", obs)
obs = env.step({"kind": "search", "registry": "PyPI", "query": "demo"})[0]
check("a registry the map gives no search API for says how to read its page", obs[0]["property"] == "no search"
      and "pypi.org/pypi/NAME/json" in obs[0]["value"], obs)
check("the registries' URLs come from the map", E.registries()["npm"]["search"].startswith("https://registry.npmjs.org/-/v1/search?text=QUERY"),
      E.registries()["npm"])


class FakeGateway:
    """Answers with the next scripted reply and keeps every request, as the gateway would see it."""

    def __init__(self, replies):
        self.replies, self.seen = list(replies), []

    def ready(self):
        return True

    def chat(self, caller, model, messages, max_tokens, call_id, tools=None):
        self.seen.append({"caller": caller, "model": model, "messages": json.loads(json.dumps(messages)), "tools": tools})
        kind, args = self.replies.pop(0)
        if kind == "words":
            return 200, {"choices": [{"message": {"content": args}}], "usage": {"prompt_tokens": 1}}
        return 200, {"choices": [{"message": {"content": "", "tool_calls": [{"id": "x", "function": {"name": kind, "arguments": json.dumps(args)}}]}}],
                     "usage": {"prompt_tokens": 1}}


agent = {"handlers": {"main": {"kind": "model", "entry": "handlers/model.py", "max_tokens": 50}},
         "parameters": {"sure_at": {"value": 0.8}, "max_steps": {"value": 6}, "window": {"value": 9000}}}
gw = FakeGateway([("fetch", {"url": "https://pypi.org/pypi/demo/json", "path": "info"}), ("answer", {"value": "MIT", "confidence": 0.9}),
                  ("fetch", {"url": "https://pypi.org/pypi/demo/json"}), ("answer", {"value": "1.2.0", "confidence": 0.95})])
lines = list(driver.run(CASES, record, agent, gw))
check("the driver prints a line a case: end, steps, final, actions", [(x["end"], x["steps"], x["final"]["answer"]) for x in lines]
      == [("terminated", 2, "MIT"), ("terminated", 2, "1.2.0")], lines)
check("every model call goes through the gateway with the environment's model and the actions as tools",
      all(s["model"] == "ollama/granite4:3b" and [t["function"]["name"] for t in s["tools"]] == ["search", "fetch", "answer", "hand_off"]
          for s in gw.seen), gw.seen[0]["tools"])
a, b = gw.seen[0]["messages"], gw.seen[1]["messages"]
check("the log only grows: each call's messages start with the last call's, byte for byte",
      json.dumps(b[:len(a)]) == json.dumps(a) and len(b) == len(a) + 2 and b[-1]["role"] == "tool", (len(a), len(b)))
check("the model is shown the question, then what came back as lines", "What licence" in a[1]["content"] and "license: MIT" in b[-1]["content"],
      b[-1]["content"][:200])
check("the model never sees a case's registry, name or shape", not any('"registry"' in json.dumps(s["messages"]) for s in gw.seen))
check("the scorer scores the answers the actions reach", score.score(map(json.dumps, lines), GOLD, {c["id"]: c for c in CASES}, record)["correct"] == 1.0)

gw = FakeGateway([("answer", {"value": "MIT", "confidence": 0.3})])
lines = list(driver.run(CASES[:1], record, agent, gw))
check("an answer below sure_at is handed up: the episode ends escalated", lines[0]["end"] == "escalated" and "not sure" in lines[0]["calls"][0]["reason"], lines)
gw = FakeGateway([("words", "MIT")])
check("a short reply in words is taken as the answer", list(driver.run(CASES[:1], record, agent, gw))[0]["final"]["answer"] == "MIT")

small = json.loads(json.dumps(agent))
small["parameters"]["window"] = {"value": 1500}
gw = FakeGateway([("fetch", {"url": "https://pypi.org/pypi/demo/json"}), ("fetch", {"url": "https://pypi.org/pypi/demo/json"}),
                  ("fetch", {"url": "https://pypi.org/pypi/demo/json"})])
lines = list(driver.run(CASES[:1], record, small, gw))
cut = [m["content"] for s in gw.seen for m in s["messages"] if m["role"] == "tool"]
check("when the window fills, the newest observation is cut to fit, and the sent part is never rewritten",
      any("[cut: the log is full]" in c for c in cut) and json.dumps(gw.seen[1]["messages"]) == json.dumps(gw.seen[-1]["messages"][:len(gw.seen[1]["messages"])]),
      [len(json.dumps(s["messages"])) for s in gw.seen])
check("and when no room is left, the step is handed up", lines[0]["end"] == "escalated" and "log is full" in lines[0]["calls"][-1]["reason"], lines[0]["calls"])

steps = json.loads(json.dumps(agent))
steps["parameters"]["max_steps"] = {"value": 2}
gw = FakeGateway([("fetch", {"url": "https://pypi.org/pypi/demo/json"}), ("answer", {"value": "MIT", "confidence": 1})])
list(driver.run(CASES[:1], record, steps, gw))
check("at max_steps the handler is told, in the new bytes, to answer or hand off",
      gw.seen[1]["messages"][-1]["content"].endswith("[last step: call answer or hand_off now]") and gw.seen[0]["tools"] == gw.seen[1]["tools"])

with tempfile.TemporaryDirectory() as d:
    p = Path(d, "r.jsonl.gz")
    record.save(p)
    check("the record saves and loads whole", E.Record(p).entries == record.entries)

print(f"{sum(checks)}/{len(checks)} checks passed")
sys.exit(0 if all(checks) else 1)
