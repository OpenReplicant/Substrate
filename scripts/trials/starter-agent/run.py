"""Trial for docs/choices/starter-agent-model.yaml (docs/tasks/starter-agent.md, stage 1): which local model can
drive a tool loop on research questions at all. Each model, through the gateway with the local-only judge key,
gets five dev questions and two tools that read GitHub's public API. Every tool result is kept on disk and
replayed, so each model sees the same world and a re-run needs no network. In the tools container:

    bin/in-tools python3 scripts/trials/starter-agent/run.py MODEL...     # e.g. granite4:3b qwen3:4b-instruct-2507-q4_K_M

Measures, per model: questions answered rightly (the gold value, read from the same API by this script, is in
the final answer), answers grounded (the gold value was in a tool result the model was shown), tool calls made
in the format asked for, model calls and seconds per question, tokens per call. Results in
.state/trials/starter-agent/results.json. No held-out case is read: the questions are written here.
"""
import hashlib
import json
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import gateway as gw  # noqa: E402

OUT = ROOT / ".state/trials/starter-agent"
CACHE = OUT / "fetched"
CACHE.mkdir(parents=True, exist_ok=True)
MAX_STEPS = 6


def fetch(url: str) -> dict:
    """GET a public JSON API once; afterwards the kept copy answers (the recording fetch, in small)."""
    f = CACHE / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".json")
    if f.exists():
        return json.loads(f.read_text())["body"]
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "research-trial"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = {"error": f"HTTP {e.code}"}
    f.write_text(json.dumps({"url": url, "read_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "body": body}))
    return body


def repo_brief(d: dict) -> dict:
    return {"full_name": d.get("full_name"), "description": d.get("description"),
            "licence": (d.get("license") or {}).get("spdx_id"), "pushed_at": d.get("pushed_at"),
            "stars": d.get("stargazers_count"), "archived": d.get("archived")}


def github_repo(full_name: str) -> dict:
    d = fetch(f"https://api.github.com/repos/{full_name.strip().strip('/')}")
    return d if "error" in d or "message" in d and "full_name" not in d else repo_brief(d)


def search_github(query: str) -> dict:
    d = fetch("https://api.github.com/search/repositories?" + urllib.parse.urlencode({"q": query, "per_page": 5}))
    return {"results": [repo_brief(x) for x in d.get("items") or []]} if "items" in d else d


TOOLS = {"github_repo": github_repo, "search_github": search_github}
SPEC = [
    {"type": "function", "function": {"name": "github_repo", "description": "Facts about one GitHub repository: licence, last push, stars.",
     "parameters": {"type": "object", "properties": {"full_name": {"type": "string", "description": "owner/name"}}, "required": ["full_name"]}}},
    {"type": "function", "function": {"name": "search_github", "description": "Search GitHub repositories by words or topic; the top five.",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
]
SYSTEM = ("You answer research questions about software from what the tools return, never from memory. Call a tool to read "
          "each fact you need. When you have the facts, reply with one short sentence that states the answer exactly as the "
          "tool gave it. If the tools cannot answer, reply: CANNOT ANSWER.")


def gold_licence(name):
    return lambda: [github_repo(name)["licence"]]


def gold_newer(a, b):
    return lambda: [max((a, b), key=lambda n: github_repo(n)["pushed_at"]).split("/")[1]]


def gold_search(query):
    return lambda: [r["full_name"] for r in search_github(query)["results"]]


QUESTIONS = [
    ("licence-1", "What licence is the GitHub repository sierra-research/tau2-bench under?", gold_licence("sierra-research/tau2-bench")),
    ("licence-2", "What licence is the GitHub repository stonybrooknlp/appworld under?", gold_licence("stonybrooknlp/appworld")),
    ("newer", "Which was pushed to more recently, sierra-research/tau-bench or sierra-research/tau2-bench? Name the repository.",
     gold_newer("sierra-research/tau-bench", "sierra-research/tau2-bench")),
    ("permissive", "Under which licence is gitleaks/gitleaks, and is that a permissive licence?", gold_licence("gitleaks/gitleaks")),
    ("find", "Find a GitHub repository that is an MCP server for dead code detection. Give its owner/name.",
     gold_search("mcp server dead code detection")),
]


def chat(url, key, model, messages):
    body = json.dumps({"model": f"ollama/{model}", "messages": messages, "tools": SPEC, "max_tokens": 500, "temperature": 0}).encode()
    req = urllib.request.Request(f"{url}/v1/chat/completions", body, {"Content-Type": "application/json", "x-bf-vk": key})
    t = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            code, d = r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        code, d = e.code, {"error": (e.read() or b"")[:300].decode("utf-8", "replace")}
    return code, d, time.perf_counter() - t


def ask(url, key, model, question):
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}]
    calls, shown, tool_calls, bad = [], [], 0, 0
    for _ in range(MAX_STEPS):
        code, d, s = chat(url, key, model, messages)
        usage = d.get("usage") or {}
        calls.append({"code": code, "s": round(s, 2), "in": usage.get("prompt_tokens"), "out": usage.get("completion_tokens")})
        if code != 200:
            return {"end": f"gateway {code}", "answer": "", "calls": calls, "tool_calls": tool_calls, "bad_tool_calls": bad, "shown": shown}
        msg = (d.get("choices") or [{}])[0].get("message") or {}
        wanted = msg.get("tool_calls") or []
        if not wanted:
            return {"end": "answered", "answer": msg.get("content") or "", "calls": calls, "tool_calls": tool_calls,
                    "bad_tool_calls": bad, "shown": shown}
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": wanted})
        for tc in wanted:
            fn = (tc.get("function") or {})
            try:
                args = fn.get("arguments")
                args = json.loads(args) if isinstance(args, str) else (args or {})
                result = TOOLS[fn.get("name")](**args)
                tool_calls += 1
            except Exception as e:      # an unknown tool or arguments it cannot take: told to the model, counted
                result, bad = {"error": f"{type(e).__name__}: {e}"}, bad + 1
            text = json.dumps(result)
            shown.append(text)
            messages.append({"role": "tool", "tool_call_id": tc.get("id"), "content": text})
    return {"end": "step limit", "answer": "", "calls": calls, "tool_calls": tool_calls, "bad_tool_calls": bad, "shown": shown}


def main(models):
    env = gw.settings()
    key, url = env["MORPHOGEN_JUDGE_KEY"], f"http://127.0.0.1:{env.get('GATEWAY_PORT') or 8090}"
    golds = {qid: [g for g in gold() if g] for qid, _, gold in QUESTIONS}
    results = {}
    for model in models:
        chat(url, key, model, [{"role": "user", "content": "ready?"}])          # load the model
        rows = []
        for qid, question, _ in QUESTIONS:
            r = ask(url, key, model, question)
            low = r["answer"].lower()
            r["right"] = any(g.lower() in low for g in golds[qid])
            r["grounded"] = r["right"] and any(g.lower() in s.lower() for g in golds[qid] for s in r["shown"])
            r.pop("shown")
            rows.append({"id": qid, **r})
            print(json.dumps({"model": model, "id": qid, "end": r["end"], "right": r["right"], "grounded": r["grounded"],
                              "model_calls": len(r["calls"]), "tool_calls": r["tool_calls"], "bad": r["bad_tool_calls"],
                              "answer": r["answer"][:120]}), flush=True)
        secs = [c["s"] for r in rows for c in r["calls"]]
        tin = [c["in"] for r in rows for c in r["calls"] if c["in"]]
        results[model] = {"right": sum(r["right"] for r in rows), "grounded": sum(r["grounded"] for r in rows), "of": len(rows),
                          "tool_calls": sum(r["tool_calls"] for r in rows), "bad_tool_calls": sum(r["bad_tool_calls"] for r in rows),
                          "model_calls": len(secs), "median_s": round(statistics.median(secs), 2) if secs else None,
                          "median_tokens_in": statistics.median(tin) if tin else None, "max_tokens_in": max(tin) if tin else None,
                          "rows": rows}
        print(json.dumps({"model": model, **{k: v for k, v in results[model].items() if k != "rows"}}), flush=True)
    (OUT / "results.json").write_text(json.dumps({"gold": golds, "results": results}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:] or ["granite4:3b"])
