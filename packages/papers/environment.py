"""The papers environment (environment.yaml; docs/contracts/environment.md): `reset`, `step`, the encoder and the gate.
Plain functions and one class; nothing here imports the store, so a judged run's driver, the handlers plugin's live run
and the record pass over the catalog use it alike.

    env = make()
    obs = env.reset(case, seed); obs, reward, terminated, truncated, info = env.step(action); env.final()

A case is {"id", "arxiv_id", "title", "abstract"}. The one action is `record`, with the fields of environment.yaml and a
`<field>_sentences` beside each: one to three numbers of the abstract's sentences, which the environment shows numbered (a
small model cannot copy a quote word for word, so it points and the environment copies). The gate: the numbers must exist
in this paper, at most three; a component_kind or slot outside the allowed values is refused; a `<field>_quote` the model
sends is ignored. The quote of an accepted field is the cited sentences' text. `reward` is always None: the score is the
scorer's. No network and no record: a paper is its own reading.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
SPEC = yaml.safe_load((HERE / "environment.yaml").read_text())
ALWAYS = {"ask": "free", "propose_handler": "propose"}
MAX_SENTENCES = 3      # sentences a field may cite


def collapse(text) -> str:
    return " ".join(str(text or "").split())


# a full stop after one of these does not end a sentence; so does one after or inside a number
ABBREVIATIONS = {"e.g", "i.e", "et al", "etc", "vs", "cf", "fig", "figs", "eq", "eqs", "sec", "no", "approx", "dr", "mr", "mrs", "ms", "prof",
                 "inc", "ltd", "co", "ca", "resp", "st", "ref", "refs", "vol", "pp", "ph.d", "u.s", "al"}
_END = re.compile(r"([.!?]+[\"')\]]*)(\s+)(?=[\"'(\[]?[A-Z0-9])")


def sentences(abstract) -> list[str]:
    """The abstract's sentences, in order: whitespace collapsed, split after . ! or ? when a capital or digit follows, but not
    after an abbreviation (e.g., i.e., et al., vs., Fig.) or inside a number or version (3.5, v2.1,
    which have no space after the point). Deterministic; a sentence is never empty."""
    text = collapse(abstract)
    out, start = [], 0
    for m in _END.finditer(text):
        head = text[start:m.start()]
        word = re.split(r"[\s(\[\"']+", head)[-1].lower() if head.strip() else ""
        if m.group(1)[0] == "." and (word in ABBREVIATIONS or word.endswith(("e.g", "i.e"))):
            continue
        out.append(text[start:m.end(1)])
        start = m.end()
    if text[start:].strip():
        out.append(text[start:])
    return out


def cited(value, n: int) -> list[int] | None:
    """The sentence numbers a field cites: a list (or a string such as "1, 3") of one to MAX_SENTENCES distinct numbers, each
    from 1 to n; None if there is none, too many, or one that is not in the paper."""
    if isinstance(value, str):
        value = re.findall(r"\d+", value)
    if isinstance(value, int) and not isinstance(value, bool):
        value = [value]
    try:
        nums = sorted({int(x) for x in value or []})
    except (TypeError, ValueError):
        return None
    return nums if 1 <= len(nums) <= MAX_SENTENCES and nums[0] >= 1 and nums[-1] <= n else None


def span_of(abstract: str, nums: list[int]) -> tuple[int, int]:
    """Where the cited sentences sit in the collapsed abstract: from the start of the first to the end of the last."""
    text, sents = collapse(abstract), sentences(abstract)
    start = sum(len(x) + 1 for x in sents[:nums[0] - 1])
    end = sum(len(x) + 1 for x in sents[:nums[-1] - 1]) + len(sents[nums[-1] - 1])
    assert text[start:end].startswith(sents[nums[0] - 1][:20])
    return start, end


def claim(subject, prop, value, source=None, at=None) -> dict:
    return {"subject": subject, "property": prop, "value": value, "source": source, "time": at}


def paper_claims(case: dict) -> list[dict]:
    """The paper only: its identifier, title and abstract as one reading. The case's other fields are for people and the scorer."""
    numbered = "\n".join(f"[{i}] {x}" for i, x in enumerate(sentences(case.get("abstract")), 1))
    text = f"arXiv {case.get('arxiv_id') or case['id']}\nTitle: {collapse(case.get('title'))}\nAbstract, by sentence:\n{numbered}"
    return [claim(f"paper:{case['id']}", "paper", text, f"paper:{case['id']}", case.get("at"))]


def gate(fields: dict, abstract: str, spec: dict = SPEC) -> tuple[dict, dict]:
    """What a `record` action says, against the abstract: ({field: {"value", "sentences", "quote"}} accepted, {field: why} refused).
    A field whose value is empty is neither. A field cites sentences (`<field>_sentences`); the quote is theirs, never the
    model's (a `<field>_quote` is ignored)."""
    f = spec["fields"]
    sents = sentences(abstract)
    accepted, refused = {}, {}
    for name in ("component_kind", "slot", "does", "result", "needs"):
        value = collapse(fields.get(name))
        if not value:
            continue
        if name in ("component_kind", "slot"):
            if value not in f[name]:
                refused[name] = f"{value!r} is not one of {', '.join(f[name])}"
                continue
            if value == f["abstain"][name]:      # says nothing about the paper, so there is nothing to cite
                accepted[name] = {"value": value}
                continue
        nums = cited(fields.get(f"{name}_sentences"), len(sents))
        if nums is None:
            refused[name] = f"cite one to {MAX_SENTENCES} sentence numbers from 1 to {len(sents)}"
        else:
            accepted[name] = {"value": value, "sentences": nums, "quote": " ".join(sents[i - 1] for i in nums)}
    return accepted, refused


class Papers:
    def __init__(self, spec: dict = SPEC):
        self.spec = spec
        self.gates = {**(spec.get("actions") or {}), **ALWAYS}
        self.max_steps = int((spec.get("episode") or {}).get("max_steps", 2))
        self.done, self.case = True, None

    def actions(self) -> list[dict]:
        """The action kinds and their arguments, as the agent is told them (its tools)."""
        f = self.spec["fields"]
        cite = "numbers of the abstract's sentences that show it, one to three, from the numbered list"
        args = {
            "component_kind": "one of " + ", ".join(f["component_kind"]),
            "component_kind_sentences": cite + " (not needed for other)",
            "slot": "one of " + ", ".join(f["slot"]),
            "slot_sentences": cite + " (not needed for none)",
            "does": "one sentence: what the component does",
            "does_sentences": cite,
            "result": "the headline claim: metric, value, benchmark, compared with what; leave empty if the abstract gives none",
            "result_sentences": cite,
            "needs": "the model or models named, and anything else stated (training, data, hardware); leave empty if none",
            "needs_sentences": cite,
        }
        return [
            {"kind": "record", "description": "Record the paper's fields. Each field cites the numbers of the sentences it rests on, "
                                              "or it is refused and stays empty. Leave a field empty rather than guess.",
             "arguments": args, "required": ["component_kind", "component_kind_sentences", "slot", "slot_sentences"]},
            {"kind": "hand_off", "description": "Hand the paper to someone else when it cannot be read as one component.",
             "arguments": {"reason": "why"}, "required": ["reason"]},
        ]

    def reset(self, case: dict, seed: int = 0) -> list[dict]:
        self.case, self.done, self.steps = case, False, 0
        self.state = {"record": None, "refused_fields": {}, "handed_off": None, "refused": [], "proposed": []}
        return paper_claims(case)

    def _note(self, prop: str, value) -> list[dict]:
        return [claim("environment", prop, value, "environment", None)]

    def step(self, action: dict):
        if self.done:
            raise RuntimeError("the episode has ended: reset first")
        self.steps += 1
        kind = action.get("kind") if isinstance(action, dict) else None
        gate_ = self.gates.get(kind)
        info, terminated = {}, False
        if gate_ is None or gate_ == "deny":
            why = "not an action here" if gate_ is None else "not allowed here"
            self.state["refused"].append({"action": action, "why": why})
            obs = self._note("refused", f"{kind!r} is {why}; the actions are {', '.join(k for k, g in self.gates.items() if g != 'deny')}")
            info["refused"] = why
        elif gate_ == "propose":
            self.state["proposed"].append(action)
            obs = self._note("proposed", f"{kind} is recorded for a person to accept, edit or ignore; it changes nothing until then")
        elif kind == "record":
            accepted, refused = gate(action, (self.case or {}).get("abstract", ""), self.spec)
            self.state["record"], self.state["refused_fields"] = accepted, refused
            obs = self._note("closed", "recorded: " + (", ".join(accepted) or "nothing")
                             + ("; refused: " + "; ".join(f"{k} ({v})" for k, v in refused.items()) if refused else ""))
            terminated = True
        elif kind == "hand_off":
            self.state["handed_off"] = str(action.get("reason") or "").strip() or "no reason given"
            obs, terminated, info["escalated"] = self._note("closed", "handed off"), True, True
        else:            # ask reaches the environment only when no such handler exists (the step loop resolves the rest)
            self.state["refused"].append({"action": action, "why": "no such handler"})
            obs, info["refused"] = self._note("refused", f"no handler {action.get('handler')!r} to ask"), "no such handler"
        truncated = not terminated and self.steps >= self.max_steps
        self.done = terminated or truncated
        return obs, None, terminated, truncated, info

    def final(self) -> dict:
        """The state the outcome is read from: the fields the gate accepted, and what it refused."""
        return {"record": self.state["record"], "fields_refused": dict(self.state["refused_fields"]),
                "handed_off": self.state["handed_off"], "refused": len(self.state["refused"]), "proposed": len(self.state["proposed"])}


def make(record=None, spec: dict = SPEC) -> Papers:
    """`record` is unused (a paper needs no recorded fetch); it is the argument the other packages' `make` takes."""
    return Papers(spec)
