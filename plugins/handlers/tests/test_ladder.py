"""The handler contract, with no database (README.md, "The contract"): what the runner refuses, how an input climbs,
and that a cheap handler never sees the outcome.

    python3 plugins/handlers/tests/test_ladder.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ladder  # noqa: E402
from ladder import Answer, Escalate, Runner, Waiting, handler, rank_key  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print(("ok  " if ok else "FAIL"), name, "" if ok else detail)


@handler("t-sure")
def sure(item, ask):
    return Answer("yes", 0.9)


@handler("t-no-confidence")
def no_confidence(item, ask):
    return Answer("yes")


@handler("t-no-reason")
def no_reason(item, ask):
    return Escalate("  ")


@handler("t-around")
def around(item, ask):
    return sure(item, ask)            # calls another handler directly: around the runner


@handler("t-through")
def through(item, ask):
    c = ask("t-sure")                 # the same, through the runner: recorded
    return Answer(c.value, 0.5)


@handler("t-crash")
def crash(item, ask):
    raise ValueError("boom")


@handler("t-unsure")
def unsure(item, ask):
    return Escalate("not sure", to="t-person")


@handler("t-peek")
def peek(item, ask):
    return Answer("saw " + str(item.get("outcome")), 1.0)


@handler("t-person")
def person(item, ask):
    return Answer(item["outcome"], 1.0) if item.get("outcome") else Waiting()


def kinds(calls):
    return [(c.handler, c.kind) for c in calls]


r = Runner(["t-no-confidence", "t-sure"], {})
calls = r.handle({})
check("an answer without a confidence is refused, and the input goes on up",
      kinds(calls) == [("t-no-confidence", "refused"), ("t-sure", "answer")], kinds(calls))
check("the refusal says why", "confidence" in (calls[0].reason or ""), calls[0].reason)

calls = Runner(["t-no-reason", "t-sure"], {}).handle({})
check("an escalation without a reason is refused", calls[0].kind == "refused" and "reason" in calls[0].reason, calls[0])

calls = Runner(["t-around"], {}).handle({})
check("a handler that calls another around the runner is refused", calls[0].kind == "refused" and "around" in calls[0].reason, calls[0])

calls = Runner(["t-through"], {}).handle({})
check("asking through the runner records the nested call, with its parent",
      kinds(calls) == [("t-through", "answer"), ("t-sure", "answer")] and calls[1].parent == 0, kinds(calls))

try:
    sure({}, None)
    check("calling a handler outside any runner raises", False)
except ladder.Unrecorded:
    check("calling a handler outside any runner raises", True)

calls = Runner(["t-crash", "t-sure"], {}).handle({})
check("a handler that crashes is refused with the crash as the reason", calls[0].kind == "refused" and "boom" in calls[0].reason, calls[0])

calls = Runner(["missing", "t-sure"], {}).handle({})
check("a handler no one registered is refused", calls[0].kind == "refused" and "no handler" in calls[0].reason, calls[0])

calls = Runner(["t-sure", "t-person"], {}, "final", reveal={"t-person"}).handle({"outcome": "no"})
check("final: the first answer ends the climb", kinds(calls) == [("t-sure", "answer")], kinds(calls))

calls = Runner(["t-sure", "t-person"], {}, "advisory", reveal={"t-person"}).handle({"outcome": "no"})
check("advisory: the input still reaches the top", kinds(calls) == [("t-sure", "answer"), ("t-person", "answer")], kinds(calls))

calls = Runner(["t-unsure", "t-sure", "t-person"], {}, "final", reveal={"t-person"}).handle({"outcome": "no"})
check("an escalation may skip rungs", kinds(calls) == [("t-unsure", "escalate"), ("t-person", "answer")], kinds(calls))

calls = Runner(["t-person"], {}, "final", reveal={"t-person"}).handle({})
check("a person with no decision yet waits", kinds(calls) == [("t-person", "waiting")], kinds(calls))

calls = Runner(["t-peek", "t-person"], {}, "advisory", reveal={"t-person"}).handle({"outcome": "secret"})
check("a handler that is not the person never sees the outcome", calls[0].value == "saw None", calls[0].value)
check("the person does", calls[1].value == "secret", calls[1].value)

entries = Runner(["alias"], {"alias": "t-sure"}).handle({})
check("a handler slug runs the implementation its entry names", kinds(entries) == [("alias", "answer")], kinds(entries))

check("rank: any person's attention is dearer than any money, money dearer than seconds",
      rank_key({"seconds": 9999}) < rank_key({"usd": 0.0001}) < rank_key({"person": 1}), "")

here = Path(__file__).resolve().parents[1]
named = [str(f.relative_to(here)) for f in here.rglob("*") if f.is_file() and f.suffix in (".py", ".json", ".yaml", ".md")
         and f.name != "test_ladder.py" and "substrate" in f.read_text().lower()]
check("nothing in the plugin names the system that uses it", not named, named)

print(f"{sum(checks)}/{len(checks)} checks passed")
sys.exit(0 if all(checks) else 1)
