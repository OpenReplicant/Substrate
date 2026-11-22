"""The voice head's router (S-170). No network: a fake embedder stands in for the gateway's embedding model.
It should:
- route by the majority of the k nearest examples, and say which examples decided
- take an owner's example (a correction) over the seed once it is added
- refuse to be built with no usable examples, and ignore examples whose route is not talk or work
- keep its seed balanced and free of the trial's held-out utterances (scripts/trials/voice-route)
- read the fast model's tool call as talk, delegate or save_note; plain words as talk; anything else as nothing
- ask for a forced tool call with thinking off and a stop at </think>; name notes the example plan accepts

    python3 scripts/tests/test_voice_route.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from voice import route  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print(("ok  " if ok else "FAIL"), name, "" if ok else detail)


WORDS = ["file", "save", "search", "computer", "note", "hello", "joke", "feel", "thanks", "capital"]


def fake_embed(texts):
    """A bag of words over a tiny vocabulary: enough to make near things near."""
    out = []
    for t in texts:
        t = t.split("Query: ", 1)[-1].lower()
        out.append([float(t.count(w)) for w in WORDS] + [0.01])
    return out


def main():
    r = route.Router(fake_embed, [("hello there", "talk"), ("tell me a joke", "talk"), ("thanks a lot", "talk"),
                                  ("save the file", "work"), ("search the computer", "work"), ("save a note", "work")])
    got, why = r.route("please save this note to a file")
    check("a request near the work examples is work", got == "work", (got, why))
    check("it says which examples decided, with their similarity", len(why["near"]) == 3
          and all({"similarity", "text", "route"} <= set(n) for n in why["near"]), why)
    got, _ = r.route("hello, and thanks for the joke")
    check("small talk near the talk examples is talk", got == "talk", got)

    r.set_examples(r.examples + [("save me a joke", "talk")] * 3)
    got, _ = r.route("save me a joke")
    check("an owner's example (three of them) outvotes the seed for its own utterance", got == "talk", got)

    try:
        route.Router(fake_embed, [("x", "maybe")])
        check("no usable examples is refused", False)
    except ValueError:
        check("no usable examples is refused", True)
    r2 = route.Router(fake_embed, [("hello", "talk"), ("save the file", "work"), ("noise", "later")])
    check("an example with an unknown route is ignored", len(r2.examples) == 2, r2.examples)

    seed = [t for t, _ in route.SEED]
    talk = sum(1 for _, x in route.SEED if x == "talk")
    check("the seed is balanced (equal talk and work)", talk * 2 == len(route.SEED), talk)
    check("the seed has no duplicates", len(set(seed)) == len(seed))
    held = ROOT / "scripts/trials/voice-route/cases.json"
    if held.exists():
        cases = {c["text"] for c in json.loads(held.read_text())}
        check("the seed holds none of the trial's held-out utterances", not cases & set(seed), cases & set(seed))

    call = lambda name, **a: {"tool_calls": [{"function": {"name": name, "arguments": json.dumps(a)}}]}  # noqa: E731
    check("a talk call is spoken text", route.tools_decision(call("talk", text=" Hi there. ")) == ("talk", "Hi there."))
    check("a delegate call carries its task", route.tools_decision(call("delegate", task="check the disk")) == ("delegate", "check the disk"))
    check("a save_note call carries its text", route.tools_decision(call("save_note", text="buy milk")) == ("save_note", "buy milk"))
    check("plain words with no tool call are talk", route.tools_decision({"content": "Mars, Venus and Earth."}) == ("talk", "Mars, Venus and Earth."))
    check("an unknown tool, bad arguments, an empty text or nothing are nothing",
          route.tools_decision(call("rm", text="x")) == ("", "") and route.tools_decision(call("talk", text=" ")) == ("", "")
          and route.tools_decision({"tool_calls": [{"function": {"name": "talk", "arguments": "{bad"}}]}) == ("", "")
          and route.tools_decision({"content": ""}) == ("", ""))
    b = route.tools_body("fast/fast", [{"role": "user", "content": "earlier"}], "now")
    check("the request forces a tool, thinking off, stops at </think>, history before the utterance",
          b["tool_choice"] == "required" and b["reasoning_effort"] == "none" and b["stop"] == ["</think>"]
          and [m["content"] for m in b["messages"][1:]] == ["earlier", "now"] and {t["function"]["name"] for t in b["tools"]} == {"talk", "delegate", "save_note"})
    import re
    plan = json.loads((ROOT / "blocks/examples/plans/note.plan.json").read_text())["trigger"]["pattern"]
    name = route.note_name("I need to buy MILK, and eggs too!")
    check("a note's name fits the example plan's trigger", name == "i-need-to-buy-milk"
          and re.match(plan, f"save a note called {name}: I need to buy milk") is not None, name)
    print(f"{sum(checks)}/{len(checks)} checks passed")
    sys.exit(0 if all(checks) else 1)


if __name__ == "__main__":
    main()
