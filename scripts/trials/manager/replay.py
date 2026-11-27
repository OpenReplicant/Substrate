"""PM-1a, the replay (docs/manager-agent.md, section 8): each scenario's message into a fresh manager session against a
fresh stub portfolio, the trace scored against the scenario's labels. Standard library only; run with python3 -I.

    python3 -I replay.py run --driver claude-code --model haiku --label haiku            # all 43, one run, sequential
    python3 -I replay.py run --driver openai-compatible --url http://127.0.0.1:8081 --label inkling \
        --extra '{"chat_template_kwargs": {"enable_thinking": false}}'
    python3 -I replay.py run --driver choice --url http://127.0.0.1:8083 --label d1
    python3 -I replay.py report results/pm1a-DATE-haiku.json results/pm1a-DATE-sonnet.json   # two arms: the table, the verdict
    python3 -I replay.py rescore results/pm1a-DATE-haiku.json                                 # score the saved traces again after a change to score.py
    python3 -I replay.py judge results/pm1a-DATE-haiku.json --model sonnet                  # optional: must-carry items by an LLM judge

`run` writes results/pm1a-<date>-<label>.json (per scenario: score, trace, final text, usage) after every scenario, and
stops at the first rate-limit error with what it has. `--only s01,s02` limits it; `--resume` skips scenarios already in the file.
"""
from __future__ import annotations

import argparse
import copy
import datetime
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python3 -I does not put the script's folder on the path

import drivers  # noqa: E402
import score as S  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def load_world(scenarios=None, fixture=None):
    sc = json.load(open(scenarios or os.path.join(HERE, "scenarios.json")))
    fx = json.load(open(fixture or os.path.join(HERE, "portfolio_fixture.json")))
    p = copy.deepcopy(sc["portfolio"])
    for pr in p["projects"]:
        pr.update(fx["projects"].get(pr["id"], {}))
    p["meter"], p["knowledge"] = fx["meter"], fx["knowledge"]
    return sc["scenarios"], p


def fresh(portfolio, scenario):
    p = copy.deepcopy(portfolio)
    for k, v in (scenario.get("given") or {}).items():
        if isinstance(v, list):
            p[k] = p.get(k, []) + v
        else:
            p[k] = v
    return p


def make_driver(a):
    if a.driver == "claude-code":
        import claude_driver  # not in the copy that runs on Kaggle
        return claude_driver.ClaudeCode(a.model, a.effort, a.prompt)
    if a.driver == "openai-compatible":
        return drivers.OpenAICompatible(a.url, a.model or "local", a.prompt, json.loads(a.extra or "{}"),
                                        name=f"openai-compatible:{a.label}", prefill=a.prefill)
    return drivers.Choice(a.url or "http://127.0.0.1:8083")


def run_all(driver, scenarios, portfolio, out_path, only=None, resume=False, log=print):
    done = {}
    if resume and os.path.exists(out_path):
        done = {r["id"]: r for r in json.load(open(out_path))["runs"]}
    runs, stopped = [], None
    for sc in scenarios:
        if only and sc["id"] not in only:
            continue
        if sc["id"] in done:
            runs.append(done[sc["id"]])
            continue
        pf = fresh(portfolio, sc)
        with tempfile.TemporaryDirectory(prefix="pm1a-") as d:
            trace_path = os.path.join(d, "trace.jsonl")
            try:
                res = driver.run(S.message_for(sc), pf, trace_path)
            except drivers.RateLimited as e:
                stopped = f"rate limit at {sc['id']}: {e}"
                break
            trace = S.load_trace(trace_path)
        sco = S.score(sc, pf, trace, res)
        runs.append({"id": sc["id"], "score": sco, "trace": trace, "final_text": res.get("final_text", ""),
                     "error": res.get("error"), "reported_model": res.get("reported_model") or res.get("model"),
                     "offered_tools": res.get("offered_tools"), "prefill": res.get("prefill")})
        log(f"{sc['id']}: {','.join(sco['tags'])} {sco['named']} routing={'ok' if sco['routing_ok'] else 'WRONG'} "
            f"{sco['wall_s']:.1f}s {sco['tokens']['output']} out" + (f" ERROR {res['error'][:80]}" if res.get("error") else ""))
        with open(out_path, "w") as f:
            json.dump({"driver": driver.name, "stopped": stopped, "runs": runs}, f, indent=1)
    with open(out_path, "w") as f:
        json.dump({"driver": driver.name, "date": datetime.date.today().isoformat(), "stopped": stopped, "runs": runs}, f, indent=1)
    return runs, stopped


def judge(path, model, prompt_scenarios=None):
    """The optional LLM judge: for each started worker's brief, which `brief_must_carry` items are present. The judge is
    not told the arm. It is a print-mode session with no tools and no MCP."""
    scenarios, _ = load_world()
    by = {s["id"]: s for s in scenarios}
    data = json.load(open(path))
    scratch = tempfile.mkdtemp(prefix="pm1a-judge-")
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE") and k != "ANTHROPIC_API_KEY"}
    for r in data["runs"]:
        items = by[r["id"]].get("brief_must_carry")
        starts = [b for b in r["score"]["briefs"]]
        if not items or not starts:
            continue
        brief = json.dumps(starts[0]["args"], indent=1)
        q = ("A manager agent wrote this brief for a worker agent. For each required item, say whether the brief states it "
             "(in substance, not necessarily in the same words). Reply with only a JSON list of true/false, in order.\n\n"
             f"Brief:\n{brief}\n\nRequired items:\n" + "\n".join(f"{i + 1}. {t}" for i, t in enumerate(items)))
        p = subprocess.run(["claude", "-p", "--model", model, "--tools", "", "--strict-mcp-config", "--setting-sources", "local",
                            "--disable-slash-commands", "--no-session-persistence", "--output-format", "json", q],
                           cwd=scratch, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=300)
        try:
            txt = json.loads(p.stdout)["result"]
            flags = json.loads(txt[txt.index("["):txt.rindex("]") + 1])
            r["score"]["must_carry"] = {"items": items, "present": flags, "share": sum(bool(f) for f in flags) / len(items)}
        except (ValueError, KeyError):
            r["score"]["must_carry"] = {"items": items, "error": (p.stdout + p.stderr)[:200]}
        print(r["id"], r["score"]["must_carry"].get("share"))
    with open(path, "w") as f:
        json.dump(data, f, indent=1)


def rescore(path):
    """Score the saved traces again with the current rules (no model call): after a change to score.py."""
    scenarios, portfolio = load_world()
    by = {s["id"]: s for s in scenarios}
    data = json.load(open(path))
    for r in data["runs"]:
        old = r["score"]
        res = {"final_text": r["final_text"], "launch_ts": 0.0, "wall_s": old["wall_s"], "tokens": old["tokens"], "error": r["error"],
               "offered_tools": r["offered_tools"], "attempts": old.get("attempts", [])}
        new = S.score(by[r["id"]], fresh(portfolio, by[r["id"]]), r["trace"], res)
        new["latency_s"] = old["latency_s"]
        new["outside_tools"], new["worked_itself"] = old["outside_tools"], old["worked_itself"] or new["code_reply"]
        if "must_carry" in old:
            new["must_carry"] = old["must_carry"]
        r["score"] = new
    with open(path, "w") as f:
        json.dump(data, f, indent=1)


def report(paths, out=None):
    scenarios, _ = load_world()
    by = {s["id"]: s for s in scenarios}
    arms = {}
    for p in paths:
        d = json.load(open(p))
        arms[os.path.basename(p).split("-")[-1].removesuffix(".json")] = d
    names = list(arms)
    ids = [s["id"] for s in scenarios if all(any(r["id"] == s["id"] for r in arms[n]["runs"]) for n in names)]
    sc = {n: [next(r["score"] for r in arms[n]["runs"] if r["id"] == i) for i in ids] for n in names}
    L = [f"# PM-1a results, {datetime.date.today().isoformat()}", "",
         f"Arms: {', '.join(f'{n} ({arms[n]['driver']})' for n in names)}. Scenarios scored: {len(ids)} of {len(scenarios)}. "
         "Runs per scenario: 1 (the design says 3). Intervals are bootstrap over scenarios (percentile, 95%).", ""]
    for n in names:
        if arms[n].get("stopped"):
            L.append(f"**{n} stopped early:** {arms[n]['stopped']}")
    if len(names) == 2:
        L += [S.table(names, sc), ""]
        f = S.falsifier(sc[names[0]], sc[names[1]])
        L += [f"## Falsifier: \"{names[0]} is reliable enough\"", "",
              f"**Verdict: {f['overall']}.**", "",
              f"1. Routing-and-delegation accuracy, {names[0]} minus {names[1]}: {100 * f['t1']['diff']:+.1f} pt, 95% interval "
              f"[{100 * f['t1']['ci'][0]:+.1f}, {100 * f['t1']['ci'][1]:+.1f}] pt: {f['t1']['verdict']}.",
              f"2. {names[0]} did the work itself in {f['t2']['n']} scenario(s) (limit: more than 1): {f['t2']['verdict']}.",
              f"3. Must-escalate scenarios {names[0]} missed that {names[1]} got: {f['t3']['n']} (limit: more than 1): {f['t3']['verdict']}.",
              "4. Live brief quality: PM-1b, not run.", ""]
        a, b = names
        L += ["## Scenarios where they differ", "", f"| Scenario | Message | Expected | {a} | {b} |", "|---|---|---|---|---|"]
        for i, x, y in zip(ids, sc[a], sc[b]):
            if (x["routing_ok"], x["tags"], x["named"]) != (y["routing_ok"], y["tags"], y["named"]):
                s = by[i]
                msg = (s.get("message") or s["event"]["signal"]).replace("|", "/")
                e = s["expected"]

                def cell(z):
                    return f"{'ok' if z['routing_ok'] else 'WRONG'}: {'+'.join(z['tags'])} {','.join(z['named']) or '-'}"
                L.append(f"| {i} | {msg[:70]} | {e['action']}{'/' + '/'.join(e.get('also', [])) if e.get('also') else ''} {e['project'] or '-'} | {cell(x)} | {cell(y)} |")
        L.append("")
    else:
        for n in names:
            L += [f"## {n}", ""]
            for key, label, fn, kind in S.METRICS:
                lo, hi = S.boot(fn, sc[n], n=2000)
                L.append(f"- {label}: {S.fmt(kind, fn(sc[n]))} {S.fmt_ci(kind, lo, hi)}")
            L.append("")
    L += ["## Every wrong routing", "", "| Arm | Scenario | Expected | Did |", "|---|---|---|---|"]
    for n in names:
        for i, z in zip(ids, sc[n]):
            if not z["routing_ok"]:
                e = by[i]["expected"]
                L.append(f"| {n} | {i} | {e['action']}{'/' + '/'.join(e.get('also', [])) if e.get('also') else ''} {e['project'] or '-'} | {'+'.join(z['tags'])} {','.join(z['named']) or '-'} |")
    L += ["", "## Checks", ""]
    for n in names:
        offs = {tuple(sorted(r.get("offered_tools") or [])) for r in arms[n]["runs"]}
        L.append(f"- {n}: tool sets offered across runs: {[list(o) for o in offs]}; models reported: "
                 f"{sorted({r.get('reported_model') or '?' for r in arms[n]['runs']})}; errors: {sum(1 for r in arms[n]['runs'] if r.get('error'))}; "
                 f"no desktop_say (closing text only): {sum(1 for z in sc[n] if z['text_only_reply'])}; failed tool calls: {sum(z['failed_calls'] for z in sc[n])}; "
                 f"scenarios over 8 tool calls: {sum(1 for z in sc[n] if z['tool_calls'] > 8)}.")
    mc = {n: [z["must_carry"]["share"] for z in sc[n] if z.get("must_carry", {}).get("share") is not None] for n in names}
    if any(mc.values()):
        L += ["", "Must-carry items present (LLM judge, not told the arm): " + "; ".join(
            f"{n} {100 * sum(v) / len(v):.0f}% over {len(v)} briefs" for n, v in mc.items() if v)]
    text = "\n".join(L) + "\n"
    if out:
        with open(out, "w") as f:
            f.write(text)
    return text


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--driver", choices=["claude-code", "openai-compatible", "choice"], required=True)
    r.add_argument("--model")
    r.add_argument("--effort", default="low")
    r.add_argument("--url")
    r.add_argument("--extra", help="JSON merged into each chat request (openai-compatible)")
    r.add_argument("--prefill", choices=["off", "on", "auto"], default="off", help="close Inkling's thinking by prefill (openai-compatible)")
    r.add_argument("--prompt")
    r.add_argument("--label", required=True)
    r.add_argument("--out")
    r.add_argument("--only")
    r.add_argument("--resume", action="store_true")
    j = sub.add_parser("judge")
    j.add_argument("path")
    j.add_argument("--model", default="sonnet")
    rs = sub.add_parser("rescore")
    rs.add_argument("path")
    p = sub.add_parser("report")
    p.add_argument("paths", nargs="+")
    p.add_argument("--out")
    a = ap.parse_args()
    if a.cmd == "run":
        scenarios, portfolio = load_world()
        out = a.out or os.path.join(HERE, "results", f"pm1a-{datetime.date.today().isoformat()}-{a.label}.json")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        runs, stopped = run_all(make_driver(a), scenarios, portfolio, out, set(a.only.split(",")) if a.only else None, a.resume,
                                log=lambda s: print(s, flush=True))
        print(f"{len(runs)} scenarios -> {out}" + (f"; STOPPED: {stopped}" if stopped else ""))
        sys.exit(2 if stopped else 0)
    elif a.cmd == "rescore":
        rescore(a.path)
    elif a.cmd == "judge":
        judge(a.path, a.model)
    else:
        print(report(a.paths, a.out))


if __name__ == "__main__":
    main()
