"""Trial for docs/choices/local-model.yaml (spec step 22): each shortlisted local model, through the gateway, as
the drift-gaps model handler, on the gaps that were withdrawn (no outcome: this trial reads no held-out case).
Measures how often the reply is a readable answer, seconds per call, and tokens. In the tools container:

    curl .../api/decisions?raised_by=eq.substrate:drift&status=eq.withdrawn > .state/trials/local-model/gaps.json
    bin/in-tools python3 scripts/trials/local-model/run.py MODEL...
"""
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "plugins/handlers"))
import gateway as gw  # noqa: E402
import handlers_plugin as hp  # noqa: E402
import ladder  # noqa: E402
import yaml  # noqa: E402

env = gw.settings()
key = gw.caller_key(env["GATEWAY_KEY_SECRET"], gw.JUDGE)
url = f"http://127.0.0.1:{env.get('GATEWAY_PORT') or 8090}"
spec = yaml.safe_load((ROOT / "streams.yaml").read_text())["streams"]["drift-gaps"]
# the withdrawn gaps, fetched by the caller (Workbench's REST, as claude-code) into .state/trials/local-model/gaps.json
gaps = json.loads((ROOT / ".state/trials/local-model/gaps.json").read_text())
results = {}
for model in sys.argv[1:]:
    calls = []

    class Timed(hp.Gateway):
        def chat(self, *a, **k):
            t = time.perf_counter()
            code, r = super().chat(*a, **k)
            calls.append({"code": code, "s": time.perf_counter() - t, "tokens": (r.get("usage") or {}).get("total_tokens"),
                          "text": ((r.get("choices") or [{}])[0].get("message") or {}).get("content") or ""})
            return code, r

    cfg = {"model": f"ollama/{model}", "answers": ["approved", "declined"], "sure_at": 0.8, "max_tokens": 400}
    ask = hp.model_handler("trial", cfg, spec["description"], Timed(url, None, None, key=key))
    ladder._permit.set("trial")
    ask({"key": "warm", "payload": {"kind": "gap", "subject": "warm-up"}, "history": []}, None)   # load the model
    calls.clear()
    kinds = []
    for g in gaps:
        ladder._permit.set("trial")
        got = ask({"key": g["key"], "payload": {"decision": g["id"], "kind": g["kind"], "subject": g["subject"]},
                   "history": []}, None)
        reason = getattr(got, "reason", "") or ""
        kinds.append("answer" if isinstance(got, ladder.Answer) else
                     "unsure" if reason.startswith("not sure") else "unreadable" if "reply" in reason else "error")
    ok = [c for c in calls if c["code"] == 200]
    results[model] = {"cases": len(gaps), "answered": kinds.count("answer"), "unsure": kinds.count("unsure"),
                      "unreadable": kinds.count("unreadable"), "errors": kinds.count("error"),
                      "median_s": round(statistics.median(c["s"] for c in calls), 2) if calls else None,
                      "mean_tokens": round(statistics.mean(c["tokens"] or 0 for c in ok), 1) if ok else None,
                      "sample": (ok[0]["text"][:160] if ok else (calls[0]["text"][:160] if calls else ""))}
    print(json.dumps({model: results[model]}), flush=True)
out = ROOT / ".state/trials/local-model/results.json"
out.parent.mkdir(parents=True, exist_ok=True)
prev = json.loads(out.read_text()) if out.exists() else {}
out.write_text(json.dumps({**prev, **results}, indent=1) + "\n")
