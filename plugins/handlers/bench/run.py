"""One model handler over a set of inputs, as a judged run makes it (Morphogen: the cell's `run`).

Reads, from the directory Morphogen names in MORPHOGEN_INPUTS (outside the repository, read-only):
    handler.json   {"slug": ..., "about": the stream's description, "config": the handler's settings (model, answers, ...)}
    cases.jsonl    one input a line: {"id", "key", "payload", "history"}; no outcome
Calls the model through the gateway at MORPHOGEN_GATEWAY with the one key the meter gave the run (WB_GATEWAY_KEY),
and prints one JSON line a case: {"id", "kind": answer|escalate, "answer", "confidence"}. The scorer (score.py,
run from the base outside the candidate) compares them with the held-out outcomes.
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import ladder  # noqa: E402
import handlers_plugin as hp  # noqa: E402

inputs = Path(os.environ["MORPHOGEN_INPUTS"])
spec = json.loads((inputs / "handler.json").read_text())
gateway = hp.Gateway(os.environ.get("MORPHOGEN_GATEWAY"), None, None, key=os.environ.get("WB_GATEWAY_KEY"))
ask = hp.model_handler(spec["slug"], spec["config"], spec["about"], gateway)
for line in (inputs / "cases.jsonl").read_text().splitlines():
    if not line.strip():
        continue
    item = json.loads(line)
    ladder._permit.set(spec["slug"])          # what the runner does before it lets a handler take an input
    got = ask(item, None)
    out = {"id": item["id"], "kind": "answer" if isinstance(got, ladder.Answer) else "escalate"}
    if isinstance(got, ladder.Answer):
        out.update(answer=got.value, confidence=got.confidence)
    print(json.dumps(out))
