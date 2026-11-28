"""Optimise manager.md with GEPA (S-224). The task model is Haiku 5.5 through the stripped-down `claude -p` session
(claude_driver.py); the reflection model is Sonnet 5.5 through `claude -p --model sonnet --tools ""`; both on the
owner's subscription, never an API key. Train scenarios feed the reflections, dev scenarios select; the held-out set is
not opened here (it is outside the repository, split.py).

    uv run --no-project --with gepa==0.1.4 python -I optimise.py --out results/gepa-2026-11-27

Budget (hard): at most --max-runs Haiku scenario runs and --max-reflections Sonnet calls in all; the run stops on the
first rate-limit error and keeps what it has. Every evaluation and every candidate is appended to <out>/log.jsonl.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import drivers  # noqa: E402
import freeze  # noqa: E402
import mgr_eval as M  # noqa: E402

REFLECTION_TEMPLATE = """I run a manager agent for one person's portfolio of projects. Its system prompt is below. The manager is a router
with a ledger: it hands work to worker agents and never does the work itself. A small, cheap model (Haiku) follows this prompt, so
the prompt must be plain, specific and short enough to be followed on every turn.
```
<curr_param>
```

Below are some of the manager's turns: the input, the tool calls it made, and feedback from a fixed scorer (the right action
and project for that input, and what the manager did instead).
```
<side_info>
```

Write an improved system prompt.
- Keep every hard rule and the whole tool and message vocabulary. Never weaken: the manager does not do work itself, one writer per
  project at a time, workers never merge or tag, the person decides merging, settings, spend, client sends and choices.
- Learn the general rule behind each mistake (when to start a worker versus message a running one versus answer from the portfolio
  versus ask versus open a decision; how to name the project; when to stay quiet) and state it as a rule or a short decision
  procedure. Do not quote, name or paraphrase an example's wording, an example's project or worker ids, or its numbers: the prompt is
  judged on different inputs, and a rule that only fits these examples will fail there.
- Do not make it much longer than it is (at most about 30% more text). Remove sentences that do not help.
- Reply with the complete new prompt in a single ``` block."""


class Budget:
    def __init__(self, max_runs, max_reflections, log_path):
        self.max_runs, self.max_reflections = max_runs, max_reflections
        self.runs = self.reflections = 0
        self.stopped = None
        self.lock = threading.Lock()
        self.log_path = log_path

    def log(self, **kw):
        with self.lock, open(self.log_path, "a") as f:
            f.write(json.dumps({"t": round(time.time(), 1), "runs": self.runs, "reflections": self.reflections, **kw}) + "\n")

    def take_runs(self, n):
        with self.lock:
            if self.runs + n > self.max_runs:
                self.stopped = f"Haiku run budget ({self.max_runs}) would be exceeded"
                raise StopRun(self.stopped)
            self.runs += n


class StopRun(Exception):
    pass


class ManagerAdapter:
    """GEPA adapter: evaluate(batch, candidate) runs each scenario under the candidate prompt; the reflective dataset is the
    input, the calls made and the scorer's explanation."""

    def __init__(self, portfolio, budget, workers=3):
        self.portfolio, self.budget, self.workers = portfolio, budget, workers
        self.propose_new_texts = None  # GEPA's own proposer with our template (GEPA 0.1.4 needs the attribute to exist)

    def evaluate(self, batch, candidate, capture_traces=False):
        from gepa.core.adapter import EvaluationBatch
        self.budget.take_runs(len(batch))
        driver = M.make_driver(candidate["manager_prompt"])
        try:
            results = M.run_many(driver, batch, self.portfolio, self.workers)
        except drivers.RateLimited as e:
            self.budget.stopped = f"rate limit: {e}"
            raise StopRun(self.budget.stopped)
        scores = [M.objective(r[0]) for r in results]
        self.budget.log(event="eval", split=[sc.get("split") for sc in batch], ids=[sc["id"] for sc in batch], scores=scores,
                        prompt_sha=__import__("hashlib").sha256(candidate["manager_prompt"].encode()).hexdigest()[:12],
                        tokens=[r[0]["tokens"]["output"] + r[0]["tokens"]["total_input"] for r in results],
                        calls=[r[0]["tool_calls"] for r in results])
        traj = [{"sc": sc, "score": r[0], "trace": r[1], "final": r[2]} for sc, r in zip(batch, results)] if capture_traces else None
        return EvaluationBatch(outputs=[r[0]["tags"] for r in results], scores=scores, trajectories=traj)

    def make_reflective_dataset(self, candidate, eval_batch, components_to_update):
        rows = []
        for t in eval_batch.trajectories:
            sc = t["sc"]
            assert sc.get("split") == "train", "reflection reads train scenarios only"
            text, calls = M.explain(sc, t["score"], t["trace"], t["final"])
            msg = sc.get("message") or f"[supervisor event] {json.dumps(sc['event'])}"
            given = sc.get("given")
            rows.append({"Inputs": msg + (f"\n(Extra state for this turn: {json.dumps(given)})" if given else ""),
                         "Generated Outputs": "\n".join(calls) + (f"\nClosing text: {t['final'][:300]}" if t["final"].strip() else ""),
                         "Feedback": text})
        return {c: rows for c in components_to_update}


class Sonnet:
    """The reflection model: `claude -p --model sonnet`, no tools, no MCP, no settings, on the subscription."""

    def __init__(self, budget, timeout=600):
        self.budget, self.timeout = budget, timeout
        self.scratch = tempfile.mkdtemp(prefix="pm-reflect-")

    def __call__(self, prompt):
        if isinstance(prompt, list):
            prompt = "\n\n".join(m.get("content", "") for m in prompt)
        with self.budget.lock:
            if self.budget.reflections >= self.budget.max_reflections:
                self.budget.stopped = f"reflection budget ({self.budget.max_reflections}) used"
                raise StopRun(self.budget.stopped)
            self.budget.reflections += 1
        env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE") and k != "ANTHROPIC_API_KEY"}
        p = subprocess.run(["claude", "-p", "--model", "sonnet", "--effort", "medium", "--tools", "", "--strict-mcp-config",
                            "--setting-sources", "local", "--disable-slash-commands", "--no-session-persistence",
                            "--output-format", "json"], input=prompt, cwd=self.scratch, env=env, capture_output=True,
                           text=True, timeout=self.timeout)
        blob = (p.stdout + p.stderr).lower()
        try:
            out = json.loads(p.stdout)
        except ValueError:
            out = {}
        if out.get("is_error") or p.returncode != 0:
            if "limit" in blob or "rate_limit" in blob or "rate limit" in blob:
                self.budget.stopped = "rate limit on the reflection model"
                raise StopRun(self.budget.stopped)
            raise RuntimeError((p.stdout + p.stderr)[:300])
        self.budget.log(event="reflection", result=out.get("result", ""), usage=out.get("usage"))
        return out.get("result", "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-runs", type=int, default=150)
    ap.add_argument("--max-reflections", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    bad = freeze.check()
    if bad:
        sys.exit(f"scoring is frozen; changed: {bad}")
    import gepa

    scenarios, portfolio = M.load_portfolio(os.path.join(HERE, "scenarios-search.json"))
    train = [s for s in scenarios if s["split"] == "train"]
    dev = [s for s in scenarios if s["split"] == "dev"]
    assert len(train) == 20 and len(dev) == 10
    os.makedirs(a.out, exist_ok=True)
    budget = Budget(a.max_runs, a.max_reflections, os.path.join(a.out, "log.jsonl"))
    seed = open(os.path.join(HERE, "manager.md")).read()
    stop_reason, result = None, None

    def stopper(state):  # checked between iterations
        return budget.stopped is not None or budget.reflections >= budget.max_reflections

    try:
        result = gepa.optimize(
            seed_candidate={"manager_prompt": seed}, trainset=train, valset=dev, adapter=ManagerAdapter(portfolio, budget),
            reflection_lm=Sonnet(budget), reflection_prompt_template=REFLECTION_TEMPLATE, reflection_minibatch_size=3,
            max_metric_calls=a.max_runs, stop_callbacks=[stopper], seed=a.seed, run_dir=os.path.join(a.out, "gepa-state"),
            display_progress_bar=False, raise_on_exception=True, candidate_selection_strategy="pareto")
    except StopRun as e:
        stop_reason = str(e)
    except Exception as e:  # keep what exists
        stop_reason = f"{type(e).__name__}: {e}"[:300]
    summary = {"gepa": gepa.__version__ if hasattr(gepa, "__version__") else "0.1.4", "haiku_runs": budget.runs,
               "reflections": budget.reflections, "stopped": budget.stopped or stop_reason}
    if result is not None:
        cands = [c["manager_prompt"] for c in result.candidates]
        summary.update({"n_candidates": len(cands), "val_scores": list(result.val_aggregate_scores), "best_idx": result.best_idx})
        for i, c in enumerate(cands):
            open(os.path.join(a.out, f"candidate-{i}.md"), "w").write(c)
    json.dump(summary, open(os.path.join(a.out, "summary.json"), "w"), indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
