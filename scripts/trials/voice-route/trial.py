"""The voice router's trial (S-170, S-171): the fast model's first tool on the held-out utterances in cases.json (never
used to write the prompt or the seed), twice, plus five requests it might wrongly say it cannot do. The first tool
counts as talk when it is talk or a quick fact on the way to talking (lookup, calculate), and as work when it does
something (delegate, save_note, read_notes, remind, search). Run in the voice head's container:

    podman exec -i -e CASES_JSON="$(cat scripts/trials/voice-route/cases.json)" substrate-voice-1 python3 - < scripts/trials/voice-route/trial.py

2026-11-22, LFM3 1.7B Q6_K on llama.cpp b12627. Talk, delegate and save_note only (S-170): held-out 12/12 twice.
With the quick tools (S-171): held-out 11/12 twice (median 0.38 s, 0.60 s; "Name three planets" searched first);
the five extra cases 5/5 twice (disk space and "Is the stack running?" delegated, notes questions read_notes).
"""
import json, os, sys, time, urllib.request
sys.path.insert(0, "/app")
from voice import route
GW, KEY = "http://gateway:8080", os.environ["VOICE_KEY"]
cases = [(c["text"], c["route"]) for c in json.loads(os.environ["CASES_JSON"])]
extra = [("How many files are in your workspace notes folder?", "work"), ("Is the stack running?", "work"), ("What did I ask you to remember?", "work"), ("Check how much free disk space my computer has.", "work"), ("Hi! What's a fun fact about honeybees?", "talk")]
for name, cs in (("held-out", cases), ("can't-cases", extra)):
    for run in (1, 2):
        ok, ts, bad = 0, [], []
        for u, want in cs:
            body = route.tools_body("fast/fast", [], u, "Sunday 22 November 2026, 12:00 (PST)")
            r = urllib.request.Request(f"{GW}/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json", "x-bf-vk": KEY})
            t = time.perf_counter(); m = json.load(urllib.request.urlopen(r, timeout=60))["choices"][0]["message"]; ts.append(time.perf_counter() - t)
            tool, arg = route.tools_decision(m)
            # the first tool: talking, or a quick fact on the way to talking, is talk; anything that does something is work
            got = "talk" if tool in ("talk", "lookup", "calculate") else "work" if tool in ("delegate", "save_note", "read_notes", "remind", "search") else "none"
            ok += got == want
            if got != want: bad.append(f"{u!r} -> {tool}: {arg[:50]!r}")
            elif tool not in ("talk", "delegate"): bad.append(f"(ok) {u!r} -> {tool}")
        ts.sort(); print(f"{name} run {run}: {ok}/{len(cs)}, median {ts[len(ts)//2]:.2f}s", *bad, sep="\n   ")
