# Task 5: the first environment's pick, and the design of the two judge checks

**Model:** the largest available. **Needs:** task 3 (done: `docs/choices/first-environment.yaml` has the candidates and the budget arithmetic), and
the owner's go-ahead to fetch and run a benchmark. **After:** `client-readiness.md` (S-97).
**Feeds:** task 6. This is direction step 1 and the design half of step 3.

## Scope

1. **The budget arithmetic, first.** For each shortlisted candidate, from task 3's numbers:
   `calls per judged run = held-out cases x calls per episode (agent + world) x 2 sides x rounds`, with rounds
   from 7 to 10 (`morphogen.yaml`'s `rounds`). Set it against 1,000 free calls a day and 20 a minute
   (OpenRouter, S-87), and against the local model at about one second a call with no cap. State how many
   held-out cases each model tier can carry in one judged run, and how many cases the sign test needs to see
   an effect of the size hoped for (at 7 paired rounds the smallest possible p is 1/128, so every round must
   agree: say what case count makes a round's score stable enough for that).
2. **The minimum-viable model** (S-97; `docs/contracts/environment.md`, "The model is held fixed"): for each
   shortlisted candidate, the cheapest model with a published score clearly off the floor, and whether it runs
   here (the local GPU has 8 GB). A candidate with no such model is rejected for now, with that as the reason.
   Keep the testing small: enough to set a baseline and see a difference, not to raise a score.
3. **A trial** (the `research` skill's step 4) of the shortlist, with that model: the world started in Podman, one `dev` case
   reset and stepped by a scripted agent with no model, the scorer run on the result. Record what ran and what
   did not.
4. **The pick**, with each rejection's reason and what would reverse it. If the need alone decides, say so.
5. **The design of the two checks** (`docs/contracts/verdict.md`, "The two checks"), specific to the pick:
   how the same-against-same candidate is made, how many times it is judged, what the worse candidate is and
   why its damage is known in advance, the labels each verdict carries, and what result sends the work back to
   the environment instead of on to step 4.
6. **The cells:** which component of the baseline is governed first, its `change`, and its `better` (the two
   metrics of `docs/contracts/cell.md` rule 3).

## Files to touch

- `docs/choices/first-environment.yaml`: `trial`, `verdict`, `pick`, `reason`, each candidate's `outcome`, and
  a `budget` block holding the arithmetic.
- `scripts/trials/first-environment/`: the trial script, images pinned.
- `docs/tasks/06-environment-and-baseline.md`: fill in what the pick settles (its "Open until task 5" list).
- `docs/contracts/environment.md`: only if the trial shows the contract is wrong; say what changed and why.
- `DECISIONS.md`: one row for the pick (it is a default).
- The map: the picked benchmark as a `component` in `options` until task 6 runs it; `scripts/map.sh export`.

## Leave alone

`morphogen.yaml` and anything under `repos/` (the cell is written in task 6, once the driver exists). Held-out
cases: the trial reads `dev` cases only, and nothing here downloads or opens a split meant to be held out.

## Ask the owner

Only if the arithmetic says no candidate fits the free tier and the local model: whether to spend money, and
how much. Recommend the cheapest option that works.

## Done when

`docs/choices/first-environment.yaml` records the pick, its trial and its budget (direction step 1's "done
when"); the trial script re-runs; `bin/morphogen structure check morphogen.yaml` reports no error;
`scripts/check.sh` passes.
