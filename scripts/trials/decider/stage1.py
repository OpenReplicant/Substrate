"""The decider trial, stage 1 (S-178): what needs the gateway. Run in the voice head's container, which has a key:

    podman exec -i -e CASES_JSON="$(cat scripts/trials/decider/cases.json)" substrate-voice-1 python3 - \
        < scripts/trials/decider/stage1.py > .state/trials/decider/stage1.json

For every case: its embedding (the store's and the voice head's embedder, qwen3-embedding 0.6b on Ollama) and the fast
model's probability for each route, read from its next token (one letter, thinking off, the answer prefilled). Prints
JSON; stage 2 reads it.
"""
import json, math, os, time, urllib.request

GW, KEY = "http://gateway:8080", os.environ["VOICE_KEY"]
DATA = json.loads(os.environ["CASES_JSON"])
ROUTES, CASES = DATA["routes"], DATA["cases"]
DESC = {  # what each route does, as the voice head's tools describe it (voice/route.py, voice/tools.py)
    "talk": "reply by talking: chat, feelings, opinions, simple things you already know",
    "lookup": "look up an encyclopedia fact (Wikipedia): people, places, science, history",
    "calculate": "do arithmetic",
    "save_note": "save a note the user dictates",
    "read_notes": "read or search the user's saved notes",
    "remind": "set a reminder for a time",
    "search": "search the web for current things: news, weather, prices, shops, reviews",
    "delegate": "hand multi-step work to the worker: files, the computer, writing documents, checking systems",
}
LETTERS = "ABCDEFGH"
INSTRUCT = "Instruct: Decide which tool or route should handle this spoken request\nQuery: "


def post(path, body):
    r = urllib.request.Request(f"{GW}{path}", json.dumps(body).encode(), {"Content-Type": "application/json", "x-bf-vk": KEY})
    with urllib.request.urlopen(r, timeout=60) as f:
        return json.load(f)


def fast_probs(text):
    opts = "\n".join(f"{LETTERS[i]}) {r}: {DESC[r]}" for i, r in enumerate(ROUTES))
    body = {"model": "fast/fast", "max_tokens": 1, "temperature": 0, "logprobs": True, "top_logprobs": 20,
            "reasoning_effort": "none",
            "messages": [{"role": "system", "content": "You route a voice assistant's requests. Answer with one letter."},
                         {"role": "user", "content": f"Request: {text!r}\nWhich route should handle it?\n{opts}"},
                         {"role": "assistant", "content": "Answer:"}]}
    t = time.perf_counter(); d = post("/v1/chat/completions", body); dt = time.perf_counter() - t
    p = {r: 0.0 for r in ROUTES}
    for x in d["choices"][0]["logprobs"]["content"][0]["top_logprobs"]:
        k = x["token"].strip()
        if len(k) == 1 and k in LETTERS[:len(ROUTES)]:
            p[ROUTES[LETTERS.index(k)]] += math.exp(x["logprob"])
    s = sum(p.values()) or 1.0
    return {r: v / s for r, v in p.items()}, s, dt


out = []
for c in CASES:
    t = time.perf_counter(); e = post("/v1/embeddings", {"model": "ollama/qwen3-embedding:0.6b", "input": [INSTRUCT + c["text"]]})
    edt = time.perf_counter() - t
    probs, mass, fdt = fast_probs(c["text"])
    out.append({**c, "embedding": e["data"][0]["embedding"], "embed_s": edt, "fast": probs, "fast_mass": mass, "fast_s": fdt})
print(json.dumps({"routes": ROUTES, "desc": DESC, "cases": out}))
