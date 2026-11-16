"""The reading environment, its scorer and the record pass's plain functions, on the dev cases: the quote gate and what it
refuses, the scorer on a perfect, an empty and an always-other run, a forged line, how a reply becomes an action, and the
order and resuming of the pass. No network, no model, no store (the pass's writes are tested in test_papers.py).

    python3 packages/papers/tests/test_reading.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PKG = ROOT / "packages/papers"
sys.path[:0] = [str(PKG), str(PKG / "plugin"), str(ROOT / "plugins/handlers")]

import environment as E  # noqa: E402
import papers_records as pr  # noqa: E402
import reading  # noqa: E402
import score as S  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print(("ok  " if ok else "FAIL"), name, "" if ok else detail)


ABS = "We propose a graph\n  memory for agents.  It cuts tokens by 81% on Bench-1, against   a flat log. It needs GPT-4."
# 1: We propose a graph memory for agents.  2: It cuts tokens by 81% on Bench-1, against a flat log.  3: It needs GPT-4.

# ---- the sentence splitter
check("a simple abstract splits at full stops, whitespace collapsed", E.sentences(ABS) == [
    "We propose a graph memory for agents.", "It cuts tokens by 81% on Bench-1, against a flat log.", "It needs GPT-4."], E.sentences(ABS))
hard = E.sentences("We use e.g. GPT-4 and Llama 3.5 (v2.1). Smith et al. showed 81.5% gains vs. Fig. 3 baselines. It works! Does it? Yes. "
                   "See Eq. 2 (i.e., the loss). Done.")
check("e.g., et al., vs., Fig., Eq., i.e., decimals and version numbers do not end a sentence",
      hard == ["We use e.g. GPT-4 and Llama 3.5 (v2.1).", "Smith et al. showed 81.5% gains vs. Fig. 3 baselines.", "It works!", "Does it?", "Yes.",
               "See Eq. 2 (i.e., the loss).", "Done."], hard)
check("a sentence ending in a quote or bracket, and one starting with a digit or bracket, split right",
      E.sentences('He said "stop." (It stopped.) 2 more things.') == ['He said "stop."', "(It stopped.)", "2 more things."], E.sentences('He said "stop." (It stopped.) 2 more things.'))
check("an empty abstract has no sentences and the text with no full stop is one", E.sentences("") == [] and E.sentences("no stop here") == ["no stop here"])
check("sentence numbers: one to three distinct, in range; a string of numbers is read too",
      E.cited([2], 3) == [2] and E.cited("1, 3", 3) == [1, 3] and E.cited([1, 2, 3, 4], 9) is None and E.cited([4], 3) is None and E.cited([0], 3) is None
      and E.cited([], 3) is None and E.cited(None, 3) is None and E.cited(["x"], 3) is None and E.cited([2, 2], 3) == [2])

# ---- the gate
acc, ref = E.gate({"component_kind": "memory", "component_kind_sentences": [1], "slot": "notes", "slot_sentences": [2],
                   "does": "A graph memory.", "does_sentences": [1], "result": "81% fewer tokens", "result_sentences": [2, 3], "needs": "", "needs_sentences": []}, ABS)
check("sentences that exist keep their field; the quote is the cited sentences' text", set(acc) == {"component_kind", "slot", "does", "result"} and not ref
      and acc["component_kind"]["quote"] == "We propose a graph memory for agents." and acc["result"]["quote"].endswith("It needs GPT-4.")
      and acc["result"]["sentences"] == [2, 3], (acc, ref))
check("a field with an empty value stays empty, and is not a refusal", "needs" not in acc and "needs" not in ref)
acc, ref = E.gate({"component_kind": "memory", "component_kind_sentences": [4]}, ABS)
check("a sentence number the paper does not have refuses the field", not acc and "component_kind" in ref, (acc, ref))
acc, ref = E.gate({"result": "x", "result_sentences": [1, 2, 3, 4]}, ABS)
check("more than three sentences is refused", not acc and "result" in ref, (acc, ref))
acc, ref = E.gate({"result": "x"}, ABS)
check("a free field that cites nothing is refused", not acc and "result" in ref, (acc, ref))
acc, ref = E.gate({"does": "x", "does_sentences": [2], "does_quote": "words the model made up"}, ABS)
check("a quote the model sends is ignored: the stored quote is the sentence's", acc["does"]["quote"] == "It cuts tokens by 81% on Bench-1, against a flat log.", acc)
acc, ref = E.gate({"component_kind": "database", "component_kind_sentences": [1], "slot": "everywhere", "slot_sentences": [1]}, ABS)
check("a component_kind or slot outside the allowed values is refused, sentences or not", not acc and set(ref) == {"component_kind", "slot"}, (acc, ref))
acc, ref = E.gate({"component_kind": "other", "slot": "none"}, ABS)
check("other and none claim nothing, so they need no sentences", acc == {"component_kind": {"value": "other"}, "slot": {"value": "none"}} and not ref, (acc, ref))
check("the span of cited sentences runs from the first's start to the last's end in the collapsed abstract",
      E.collapse(ABS)[slice(*E.span_of(ABS, [2, 3]))] == "It cuts tokens by 81% on Bench-1, against a flat log. It needs GPT-4.")

# ---- the environment
env = E.make()
obs = env.reset({"id": "1", "arxiv_id": "1", "title": "T", "abstract": ABS, "outcome": "x"}, 0)
check("the observation is one claim, the abstract in numbered sentences, nothing of an answer",
      len(obs) == 1 and "[1] We propose a graph memory" in obs[0]["value"] and "[3] It needs GPT-4." in obs[0]["value"] and "outcome" not in obs[0]["value"], obs)
_, reward, term, trunc, info = env.step({"kind": "record", "component_kind": "memory", "component_kind_sentences": [1], "result": "y", "result_sentences": [9]})
check("record ends the episode, reward is None, the refused field is in the final state",
      term and reward is None and env.final()["record"] == {"component_kind": {"value": "memory", "sentences": [1], "quote": "We propose a graph memory for agents."}}
      and "result" in env.final()["fields_refused"], env.final())
try:
    env.step({"kind": "record"})
    check("a step after the end raises", False)
except RuntimeError:
    check("a step after the end raises", True)
env.reset({"id": "1", "abstract": ABS}, 0)
_, _, term, _, info = env.step({"kind": "hand_off", "reason": "a survey"})
check("hand-off is allowed and ends the episode as escalated", term and info.get("escalated") and env.final()["handed_off"] == "a survey")
env.reset({"id": "1", "abstract": ABS}, 0)
_, _, term, _, info = env.step({"kind": "fetch", "url": "x"})
check("an action of another kind is refused and recorded; the episode goes on", info.get("refused") and not term and env.final()["refused"] == 1)

# ---- the dev cases and the scorer
cases = [json.loads(l) for l in (PKG / "cases/dev.jsonl").read_text().splitlines()]
gold = {d["id"]: d["answer"] for d in map(json.loads, (PKG / "cases/dev.outcomes.jsonl").read_text().splitlines())}
by_id = {c["id"]: c for c in cases}
check("40 dev cases with a reference each, ids equal", len(cases) == 40 and set(by_id) == set(gold))
bad = [(cid, f) for cid, a in gold.items() for f in E.gate(a, by_id[cid]["abstract"])[1]]
check("every reference cites sentences the abstract has, passes the same gate, and every reference field is kept", not bad, bad[:3])
kinds = {a["component_kind"] for a in gold.values()}
check("the dev cases cover at least ten of the fourteen kinds", len(kinds) >= 10 and kinds <= set(E.SPEC["fields"]["component_kind"]), kinds)


def lines(action):
    return [json.dumps({"id": cid, "actions": [action(cid)] if callable(action) else [action]}) for cid in gold]


def scored(ls):
    return S.score(ls, gold, by_id)


perfect = scored(lines(lambda cid: {"kind": "record", **gold[cid]}))
check("replaying the reference scores 1 on every field", perfect["correct"] == 1.0 and all(perfect[f] == 1.0 for f in S.FIELDS), perfect)
fl = S.floors(gold, by_id)
check("an agent that hands everything off scores 0", fl["floor_nothing"] == 0.0, fl)
check("an agent that records every field empty gets only the cases whose reference leaves result or needs empty",
      abs(fl["floor_empty"] - 14 / 160) < 1e-9 and scored(lines({"kind": "record"}))["component_kind"] == 0.0, fl)
check("an agent that always records other / none scores the declared floor", abs(fl["floor_constant"] - E.SPEC["outcome"]["floor"]["constant"]) < 5e-4, fl)
check("the headline is the mean of the four field agreements", abs(perfect["correct"] - sum(perfect[f] for f in S.FIELDS) / 4) < 1e-9)

# one case right on kind and slot, wrong on sentences
cid = cases[0]["id"]
g0 = gold[cid]
one = scored([json.dumps({"id": cid, "actions": [{"kind": "record", "component_kind": g0["component_kind"], "component_kind_sentences": g0["component_kind_sentences"],
                                                 "slot": g0["slot"]}]})])
check("kind and slot are scored apart from the sentences", one["component_kind"] == 1 / 40 and one["slot"] == 1 / 40 and one["result"] == 0, one)
# result: any shared sentence agrees (the reference's, plus another); a different sentence does not
ref_s = g0["result_sentences"]
n = len(E.sentences(cases[0]["abstract"]))
other = next(k for k in range(1, n + 1) if k not in ref_s)
share = scored([json.dumps({"id": cid, "actions": [{"kind": "record", "result": "z", "result_sentences": [ref_s[0], other]}]})])
apart = scored([json.dumps({"id": cid, "actions": [{"kind": "record", "result": "z", "result_sentences": [other]}]})])
check("a result that shares a sentence with the reference's agrees; one with none in common does not", share["result"] == 1 / 40 and apart["result"] == 0, (share, apart, ref_s))
wrong = scored(lines(lambda c: {"kind": "record", **{**gold[c], "component_kind": "memory", "component_kind_sentences": [99]}}))
check("a field citing a sentence the paper lacks is empty, so it cannot agree", wrong["component_kind"] == 0.0 and wrong["slot"] == 1.0, wrong)
forged = scored([json.dumps({"id": c, "actions": [{"kind": "hand_off", "reason": "x"}], "reward": 1, "score": 1,
                             "final": {"record": gold[c], "handed_off": None}}) for c in gold])
check("a made-up final, reward or score does not raise the score", forged["correct"] == 0.0, forged)
dup = scored(lines(lambda c: {"kind": "record", **gold[c]}) + lines(lambda c: {"kind": "record", **gold[c]})[:5])
check("a duplicate id scores as the floor for that case", abs(dup["correct"] - 35 / 40) < 1e-9, dup)
many = scored([json.dumps({"id": c, "actions": [{"kind": "record", **gold[c]}] * 3}) for c in gold])
check("more actions than the episode allows score as the floor", many["correct"] == 0.0, many)
check("a line the scorer cannot read scores as the floor", scored(["not json", "{"])["correct"] == 0.0)

# ---- a reply into an action
tool = {"choices": [{"message": {"tool_calls": [{"function": {"name": "record", "arguments": json.dumps({"component_kind": "memory"})}}]}}]}
words = {"choices": [{"message": {"content": 'Here: {"component_kind": "routing", "slot": "route"} done'}}]}
none = {"choices": [{"message": {"content": "I cannot say."}}]}
check("a tool call is the action", reading.action_of(tool)[0] == {"kind": "record", "component_kind": "memory"})
check("a JSON object in words with the fields is a record", reading.action_of(words)[0]["slot"] == "route")
check("anything else is no action, with the reason", reading.action_of(none)[0] is None and "no tool call" in reading.action_of(none)[1])
check("the same model and instructions hash the same; another model or another instruction does not",
      reading.digest("a", "m") == reading.digest("a", "m") != reading.digest("a", "n") and reading.digest("a", "m") != reading.digest("b", "m"))

# ---- the pass: order, skipping, a fake gateway
papers = [{"slug": "a", "arxiv_id": "a", "abstract": "x", "testable": False, "listing_count": 9},
          {"slug": "b", "arxiv_id": "b", "abstract": "x", "testable": True, "listing_count": 2},
          {"slug": "c", "arxiv_id": "c", "abstract": "x", "testable": True, "listing_count": 5},
          {"slug": "d", "arxiv_id": "d", "abstract": "", "testable": True, "listing_count": 99},
          {"slug": "e", "arxiv_id": "e", "abstract": "x", "testable": None, "listing_count": 1}]
check("testable first, most-listed first, then the rest; a paper with no abstract is not read", [p["slug"] for p in pr.order(papers)] == ["c", "b", "a", "e"])


class Gateway:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def ready(self):
        return True

    def chat(self, caller, model, messages, max_tokens, call_id, tools=None):
        self.calls.append((caller, model, messages, tools))
        return self.replies.pop(0)


good = (200, {"usage": {"prompt_tokens": 100, "completion_tokens": 20}, "choices": [{"message": {"tool_calls": [{"function": {
    "name": "record", "arguments": json.dumps({"component_kind": "memory", "component_kind_sentences": [1],
                                                "result": "r", "result_sentences": [40]})}}]}}]})
g = Gateway([good])
r = pr.read({"slug": "p", "arxiv_id": "p", "title": "T", "abstract": ABS}, "fixed", "m", g, "handler:papers-main")
fields, quotes = pr.fields_of(r["final"])
check("a paper is one call, as the agent's caller, offering the two tools; the gate keeps what cites a sentence it has",
      len(g.calls) == 1 and g.calls[0][0] == "handler:papers-main" and [t["function"]["name"] for t in g.calls[0][3]] == ["record", "hand_off"]
      and fields == {"component_kind": "memory", "slot": None, "does": None, "result": None, "needs": None}
      and quotes["component_kind"]["sentences"] == [1], (fields, quotes))
check("the abstract and the instructions are in the call", "[1] We propose a graph memory" in g.calls[0][2][1]["content"] and g.calls[0][2][0]["content"] == "fixed")
slept = []
g = Gateway([(429, {}), (429, {}), good])
r = pr.read({"slug": "p", "arxiv_id": "p", "title": "T", "abstract": ABS}, "f", "m", g, "c", sleep=slept.append)
check("a 429 waits 30 s, then 60 s, and tries again", "final" in r and slept == [30, 60], (r, slept))
g = Gateway([(429, {})] * 4)
r = pr.read({"slug": "p", "arxiv_id": "p", "title": "T", "abstract": ABS}, "f", "m", g, "c", sleep=lambda s: None)
check("after three waits it gives up and says the next run should resume", "error" in r and r["retry"] is True, r)
r = pr.read({"slug": "p", "arxiv_id": "p", "title": "T", "abstract": ABS}, "f", "m", Gateway([(200, {"choices": [{"message": {"content": "no"}}]})]), "c")
check("a reply with no action is an error that is not retried", "error" in r and r["retry"] is False, r)

# ---- several papers in one call
A1 = "Alpha builds a graph memory for agents. It cuts tokens by 81% on Bench-1."     # two sentences
A2 = "Beta routes each request to a cheaper model."                                  # one sentence
P1 = {"slug": "p1", "arxiv_id": "1111.1", "title": "One", "abstract": A1}
P2 = {"slug": "p2", "arxiv_id": "2222.2", "title": "Two", "abstract": A2}
P3 = {"slug": "p3", "arxiv_id": "3333.3", "title": "Three", "abstract": "Gamma is a survey of agents."}


def batch_reply(*records):
    return (200, {"usage": {"prompt_tokens": 300, "completion_tokens": 90}, "choices": [{"message": {"tool_calls": [{"function": {
        "name": "record_batch", "arguments": json.dumps({"records": list(records)})}}]}}]})


g = Gateway([batch_reply(
    {"id": "1111.1", "component_kind": "memory", "component_kind_sentences": [1]},
    {"id": "2222.2", "component_kind": "routing", "component_kind_sentences": [2],                         # a sentence only its neighbour has
     "slot": "route", "slot_sentences": [1]},
    {"id": "9999.9", "component_kind": "other"})])                                                          # not in the batch
r = pr.read_batch([P1, P2, P3], "fixed", "m", g, "handler:papers-main")
check("a batch is one call, with every paper under its id and numbered sentences, and the record_batch tool",
      len(g.calls) == 1 and all(f"=== {i} ===" in g.calls[0][2][1]["content"] for i in ("1111.1", "2222.2", "3333.3"))
      and [t["function"]["name"] for t in g.calls[0][3]] == ["record_batch"] and "record_batch" in g.calls[0][2][0]["content"], g.calls[0][3])
check("a sentence number only a neighbour in the same batch has is refused; the paper's own sentence is kept",
      "component_kind" in r["finals"]["2222.2"]["fields_refused"] and r["finals"]["2222.2"]["record"].get("slot")
      and not r["finals"]["2222.2"]["record"].get("component_kind") and r["finals"]["1111.1"]["record"]["component_kind"]["value"] == "memory"
      and r["finals"]["2222.2"]["record"]["slot"]["quote"] == "Beta routes each request to a cheaper model.", r["finals"])
check("an id that is not in the batch is ignored", "9999.9" not in r["finals"] and "9999.9" not in r["skipped"], r)
check("a paper the answer skipped has no final state, and is listed to be asked again", r["skipped"] == ["3333.3"] and "3333.3" not in r["finals"], r)
check("the call's tokens are reported once", r["usage"] == {"prompt_tokens": 300, "completion_tokens": 90})
g = Gateway([batch_reply({"id": "1111.1", "component_kind": "other"}, {"id": "1111.1", "component_kind": "memory", "component_kind_sentences": [1]})])
r = pr.read_batch([P1], "f", "m", g, "c")
check("the first record of an id counts", r["finals"]["1111.1"]["record"] == {"component_kind": {"value": "other"}}, r)
check("a batch answer with no records is an error, not retried",
      pr.read_batch([P1], "f", "m", Gateway([(200, {"choices": [{"message": {"content": "no"}}]})]), "c")["retry"] is False)
check("records in words as JSON are read too", reading.records_of({"choices": [{"message": {"content": 'x {"records": [{"id": "1"}]}'}}]})[0] == [{"id": "1"}])
check("a batch changes the digest, so a paper read one at a time is read again", reading.digest(reading.batch_fixed("a"), "m") != reading.digest("a", "m"))

print(f"{sum(checks)}/{len(checks)} checks passed")
sys.exit(0 if all(checks) else 1)
