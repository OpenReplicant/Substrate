"""The voice head's router (S-170). No network: a fake embedder stands in for the gateway's embedding model.
It should:
- route by the majority of the k nearest examples, and say which examples decided
- take an owner's example (a correction) over the seed once it is added
- refuse to be built with no usable examples, and ignore examples whose route is not talk or work
- keep its seed balanced and free of the trial's held-out utterances (scripts/trials/voice-route)
- read the fast model's tool call as talk, delegate or save_note; plain words as talk; anything else as nothing
- ask for a forced tool call with thinking off and a stop at </think>; the final step offers only talk and delegate
- read a talk call's text as it streams, escapes split across chunks included
- quick tools (S-171): notes saved and found, reminders' times read or refused, arithmetic only, Wikipedia and
  search results shaped from fake answers

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
    check("a quick tool call carries its arguments as JSON", route.tools_decision(call("save_note", text="buy milk")) == ("save_note", '{"text": "buy milk"}'))
    check("plain words with no tool call are talk", route.tools_decision({"content": "Mars, Venus and Earth."}) == ("talk", "Mars, Venus and Earth."))
    check("an unknown tool, bad arguments, an empty text or nothing are nothing",
          route.tools_decision(call("rm", text="x")) == ("", "") and route.tools_decision(call("talk", text=" ")) == ("", "")
          and route.tools_decision({"tool_calls": [{"function": {"name": "talk", "arguments": "{bad"}}]}) == ("", "")
          and route.tools_decision({"content": ""}) == ("", ""))
    b = route.tools_body("fast/fast", [{"role": "user", "content": "earlier"}], "now", "Sunday 22 November 2026, 12:00 (PST)")
    check("the request forces a tool, thinking off, stops at </think>, history before the utterance, the time in the prompt",
          b["tool_choice"] == "required" and b["reasoning_effort"] == "none" and b["stop"] == ["</think>"]
          and [m["content"] for m in b["messages"][1:]] == ["earlier", "now"] and "22 November 2026" in b["messages"][0]["content"]
          and {t["function"]["name"] for t in b["tools"]} == {"talk", "delegate"} | route.QUICK_NAMES)
    f = route.tools_body("fast/fast", [], "now", final=True)
    check("the last step offers only talk and delegate", {t["function"]["name"] for t in f["tools"]} == {"talk", "delegate"})
    t = route.TalkText()
    got = "".join(t.feed(c) for c in ['{"te', 'xt": "Hel', 'lo, \\"you\\"! \\u00e', '9t\\u00e9.', '"}'])
    check("a talk call's text is read as it streams, split escapes included", got == 'Hello, "you"! été.', got)
    ev = list(route.stream_events([b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"c1","function":{"name":"talk","arguments":"{\\"text"}}]}}]}',
                                   b'data: {"choices":[{"delta":{"content":"hi"}}]}', b"data: [DONE]", b'data: {"choices":[{"delta":{"content":"late"}}]}']))
    check("stream lines become tool and content events, up to [DONE]", ev == [("tool", 0, "c1", "talk", '{"text'), ("content", "hi")], ev)
    sp = route.speakable("- **NASA's rover** found `ice` 🚀\n2. Then #more")
    check("speech loses markdown, list marks and emoji", sp == "NASA's rover found ice Then more", sp)
    import datetime as dt
    import re
    import tempfile
    from voice import tools as T
    root = tempfile.mkdtemp()
    check("a note is saved under notes/, a second with the same words gets its own file",
          T.save_note(root, "Buy milk") == "saved as notes/buy-milk.txt" and T.save_note(root, "buy milk") == "saved as notes/buy-milk-2.txt")
    T.save_note(root, "Call the dentist on Monday")
    check("notes are read, all or about a topic", "call-the-dentist-on-monday" in T.read_notes(root)
          and "milk" not in T.read_notes(root, "dentist") and T.read_notes(root, "piano").startswith("no notes"))
    now = dt.datetime(2026, 11, 22, 12, 0, tzinfo=dt.timezone(dt.timedelta(hours=-8)))
    r1, rec1 = T.remind("stretch", "in 20 minutes", now)
    r2, rec2 = T.remind("call mum", "2026-11-23T09:30", now)
    check("a reminder's time is read as 'in N minutes' or local ISO", rec1["due"] == "2026-11-22T12:20:00-08:00"
          and rec2["due"] == "2026-11-23T09:30:00-08:00" and "Monday" in r2, (rec1, rec2, r2))
    check("a past or unreadable time, or no text, is refused with a reason", T.remind("x", "2026-11-21T09:00", now)[1] is None
          and T.remind("x", "soonish", now)[0].startswith("error") and T.remind(" ", "in 5 minutes", now)[1] is None)
    check("arithmetic is exact and only arithmetic", T.calculate("17.5 * 4") == "17.5 * 4 = 70" and T.calculate("2^10").endswith("= 1024")
          and T.calculate("__import__('os')").startswith("error") and T.calculate("1/0").startswith("error")
          and T.calculate("9**9999").startswith("error"))
    pages = {"search": {"pages": [{"key": "Octopus", "title": "Octopus"}]}, "summary": {"title": "Octopus", "extract": "Octopuses have three hearts."}}
    wiki = T.lookup("octopus hearts", get=lambda url, timeout=6: pages["search" if "search/page" in url else "summary"])
    check("a lookup is Wikipedia's summary of the best match", wiki == "Wikipedia, Octopus: Octopuses have three hearts.", wiki)
    check("no article, or Wikipedia not answering, is said plainly", T.lookup("zzz", get=lambda u, timeout=6: {"pages": []}).startswith("Wikipedia has no")
          and T.lookup("x", get=lambda u, timeout=6: (_ for _ in ()).throw(OSError())).startswith("error"))
    res = {"results": [{"title": "Mars rover news", "url": "https://example.org/a", "content": "The rover found ice."}] * 6}
    found = T.search("mars rover", "http://search:8080", get=lambda url, timeout=8: res)
    check("search gives at most four results with their site", found.count("\n") == 3 and "(example.org): The rover found ice." in found, found)
    check("search with no engine set says so", T.search("x", "").startswith("error"))
    plan = json.loads((ROOT / "blocks/examples/plans/note.plan.json").read_text())["trigger"]["pattern"]
    name = route.note_name("I need to buy MILK, and eggs too!")
    check("a note's name fits the example plan's trigger", name == "i-need-to-buy-milk"
          and re.match(plan, f"save a note called {name}: I need to buy milk") is not None, name)
    print(f"{sum(checks)}/{len(checks)} checks passed")
    sys.exit(0 if all(checks) else 1)


if __name__ == "__main__":
    main()
