# PM-1a's scoring, frozen for the manager-prompt cell (S-224), 2026-11-27

From here on `score.py` and what it scores against do not change; `freeze.py check` (run by `optimise.py` and `judge.py`
before anything else, and by `scripts/tests/test_manager_trial.py`) fails if any of these files differ from the hashes in
`pm1a-scoring-frozen.json`: `score.py`, `stub_pm.py`, `portfolio_fixture.json`, `scenarios.json`, `split.json`,
`scenarios-search.json`. A change to a rule is a new version with a new file of this kind, never an edit.

**The rules** (docstring of `score.py`, version `pm1a-score-2026-11-27`): a trace's tags are start, message, stop, decision,
ask, or else answer or ack; `action_ok` needs every tag to be the expected action or an `also`; `project_ok` needs the projects
named to be exactly the expected one (an `ack` that did nothing is not scored); `routing_ok` is both. Delegation recall,
escalation precision and recall, "did the work itself" (a tool outside the offered nine, or more than 10 lines of code in a reply)
as in the module.

**Before and after the change that PM-1a made to its own rules** (recorded together, Haiku 5.5, one run per scenario, the same
43 traces):

| Scoring | Routing accuracy | Notes |
|---|---|---|
| first rules (never committed), as `pm1a-2026-11-27.md` records | 67% | cannot be recomputed: the file was edited before its first commit |
| frozen rules (this version), `replay.py rescore` on the saved traces | 81.4% [70, 93]% | reproduced again on 2026-11-27 before freezing: action 83.7%, project 86.7%, delegation recall 61.1%, did the work itself 0, escalation precision 82.4%, recall 92.9% |

The four changes (a reply is the closing text for a person's message only; `kernel` as a word is not the project;
kernel_search's project is not a routing claim; an `ack` that did nothing is not scored on project) were made before any
optimisation, and the 14-point difference is theirs, not a model's.
