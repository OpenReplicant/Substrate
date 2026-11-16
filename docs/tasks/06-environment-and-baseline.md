# Task 6: the environment and the plain-agent baseline

**Model:** Opus. **Needs:** task 5 (the pick), `meter-factors.md`. **Feeds:** direction steps 3 and 4.
Build against `docs/contracts/environment.md` and `docs/contracts/cell.md`; where they do not fit what you
find, stop and say so instead of bending either.

## Scope

Direction step 2: the picked environment wired, and a plain agent that runs it end to end with every model
call counted at the gateway. Nothing is judged yet beyond one smoke run.

1. **The world**: `packages/<slug>/environment.py` wrapping the picked benchmark behind `reset(case, seed)` and
   `step(action)`. The benchmark's own code is fetched at a pinned commit by a script, not copied in.
2. **The declaration**: `packages/<slug>/environment.yaml` and `agent.yaml`, as the contract's example.
3. **The driver and the scorer**: `driver.py` (the cell's `run`: reads `MORPHOGEN_INPUTS/cases.jsonl`, prints
   one line an episode) and `score.py` (the cell's `score`: reads those lines and `MORPHOGEN_PRIVATE`, prints
   the metrics). Model them on `plugins/handlers/bench/run.py` and `score.py`. The scorer replays each
   episode's `actions` against a fresh world and scores the state it reaches itself (the contract's "forged
   `final`").
4. **The baseline**: one model handler (`ladder.py`'s contract) that turns an observation into an action, on
   the local model through the gateway. One prompt, no memory, no recall, no second handler. It is meant to
   be beaten.
5. **Cases**: `cases/dev.jsonl` in the repository; a script (as `scripts/judged.py` does for drift gaps) that
   writes `inputs/`, `search/` and `private/` outside the repository and prints the lines for
   `morphogen.local.yaml`.
6. **The contract test**: `scripts/contract.sh environment <slug>`, the five checks in the contract.
7. **The cell**: in `morphogen.yaml`, as task 5 designed it. The map gets the environment and the baseline as
   `component` items (rule 8), then `scripts/map.sh export`.

## Files to touch

`packages/<slug>/` (new; S-102), `scripts/` (the cases script, the fetch script, `contract.sh`'s new interface),
`morphogen.yaml`, `streams.yaml` only if the environment's streams are declared there instead of in its own
file, `catalog-info.yaml` by export only, `deploy/tools/Containerfile` if the world needs a package,
`DECISIONS.md` (one row), `.env.example` if a setting is added.

## Leave alone

- `repos/morphogen`: if the judge cannot do something this needs, write it up for the `upstream` skill and
  stop; do not patch the clone.
- `workbench/`: nothing in it may know about environments.
- `plugins/handlers/ladder.py`: the handler contract is used as it is. A change to it is its own task.
- The existing cell `component:model-handler` and its bench.
- Held-out cases: written by the script, never opened, printed or copied into the repository, a prompt or a
  test. Build and debug on `dev` only.
- No second handler, no compile-down, no router: those are step 4's candidates.

## Open until task 5

The slug; which benchmark commit; how many held-out cases; the outcome metric's name and floors; whether the
world plays a customer with a model (then its calls use a second gateway key, per the contract); the first
governed component.

## Done when

- `scripts/contract.sh environment <slug>` passes;
- the baseline runs every `dev` case end to end, and the gateway's record shows a call for every model call
  the driver made (none unseen, none under another key);
- one judged smoke run completes (base against a trivially different candidate) and its verdict is in the
  Knowledge Kernel with `metered.*` and `scored.*` metrics, pass or fail;
- `bin/morphogen structure check morphogen.yaml` reports no error; `scripts/test.sh` and `scripts/check.sh` pass.
