"""The voice router's workload for Morphogen (cell voice-route, S-193): the fast model's first tool for each utterance in
$MORPHOGEN_INPUTS/utterances.json, through the gateway Morphogen joins to the run ($MORPHOGEN_GATEWAY) with the key and
call tag its meter gave ($GATEWAY_KEY, $GATEWAY_CALL_TAG). Prints one JSON line per case, then a closing line.
Standard library only: it runs in the sandbox image with the tree mounted read-only."""
import json, os, sys, urllib.request
sys.path.insert(0, os.getcwd())
from voice import route  # noqa: E402

GW, KEY, TAG = os.environ["MORPHOGEN_GATEWAY"], os.environ["GATEWAY_KEY"], os.environ["GATEWAY_CALL_TAG"]
NOW = "Monday 23 November 2026, 12:00 (PST)"   # fixed, so every run asks the same question
cases = json.load(open(os.path.join(os.environ["MORPHOGEN_INPUTS"], "utterances.json")))
for n, c in enumerate(cases):
    body = route.tools_body("fast/fast", [], c["text"], NOW)
    req = urllib.request.Request(f"{GW}/v1/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json", "x-bf-vk": KEY, "x-wb-call": f"{TAG}-{n}"})
    try:
        tool, _ = route.tools_decision(json.load(urllib.request.urlopen(req, timeout=60))["choices"][0]["message"])
    except Exception as e:  # a failed call is a wrong answer, not a crash
        tool = "error:" + type(e).__name__
    print(json.dumps({"case": c["id"], "tool": tool or "none"}), flush=True)
print("done")
