"""The voice router's trial (S-170): the fast model's tool choice on the held-out utterances in cases.json (never
used to write the prompt or the seed), twice, plus three requests it might wrongly say it cannot do.
Run in the voice head's container (it has the router and VOICE_KEY):

    podman exec -i -e CASES_JSON="$(cat scripts/trials/voice-route/cases.json)" substrate-voice-1 python3 - < scripts/trials/voice-route/trial.py

2026-11-22, LFM3 1.7B Q6_K on llama.cpp b12627: held-out 12/12 and 12/12 (median 0.35 s, 0.43 s); the three
"can't" cases 2/3 twice ("Is the stack running?" came back as talk, echoing the question).
"""
import json, os, sys, time, urllib.request
sys.path.insert(0, "/app")
from voice import route
GW, KEY = "http://gateway:8080", os.environ["VOICE_KEY"]
cases = [(c["text"], c["route"]) for c in json.loads(os.environ["CASES_JSON"])]
extra = [("How many files are in your workspace notes folder?", "work"), ("Is the stack running?", "work"), ("What did I ask you to remember?", "work")]
for name, cs in (("held-out", cases), ("can't-cases", extra)):
    for run in (1, 2):
        ok, ts, bad = 0, [], []
        for u, want in cs:
            body = route.tools_body("fast/fast", [], u)
            r = urllib.request.Request(f"{GW}/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json", "x-bf-vk": KEY})
            t = time.perf_counter(); m = json.load(urllib.request.urlopen(r, timeout=60))["choices"][0]["message"]; ts.append(time.perf_counter() - t)
            tool, arg = route.tools_decision(m)
            got = "talk" if tool == "talk" else "work" if tool in ("delegate", "save_note") else "none"
            ok += got == want
            if got != want: bad.append(f"{u!r} -> {tool}: {arg[:50]!r}")
        ts.sort(); print(f"{name} run {run}: {ok}/{len(cs)}, median {ts[len(ts)//2]:.2f}s", *bad, sep="\n   ")
