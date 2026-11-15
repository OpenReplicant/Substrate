# Task 3: benchmark checks

**Model:** Sonnet. **Needs:** nothing. **Feeds:** task 5 (the pick). Read `docs/direction.md`,
`docs/contracts/environment.md` and the `research` skill first.

## Scope

Find out, for each benchmark that could be the first environment, whether Substrate may use it and what a run
costs. Record the need and the candidates through the `research` skill's steps 1 to 3. **Do not pick, and do
not run a trial**: the pick and the budget arithmetic are task 5's.

The shortlist in `docs/direction.md` is from memory and unverified, names included: policy-bound support
simulations (the τ-bench family), OmegaUse-OfficeVal, TheAgentCompany. Confirm each exists under that name, and
search for at least two more for support or back-office work that the shortlist missed. A benchmark that
cannot be found is recorded as rejected, with the searches that failed.

## For each candidate, from its own repository or paper, with the URL and the date read

1. **Licence** of the code and, separately, of the data. Quote the LICENSE file when the registry says
   NOASSERTION.
2. **Upkeep:** last release or tagged commit, open issues that say it is broken, whether the leaderboard still
   takes entries.
3. **How a run is scored:** what the outcome is read from (a final database state, a checker script, a
   model's opinion), whether that scorer can run with no model call, and whether it can run outside the agent's
   process.
4. **Model calls per task:** the agent's (median and maximum steps, as the paper reports them) and, separately,
   the world's (a simulated customer played by a model, a model-based grader).
5. **Cases:** how many tasks, whether a held-out split exists or fresh cases can be generated, and whether the
   test set is public (then it counts as `dev`, per the environment contract).
6. **What it needs to run:** containers, services, disk, a GPU, a browser, network access during a run.
7. **Fit to the contract:** can the world be reset and stepped; is it deterministic for a case and seed; can
   actions be replayed without a model.

## Files to touch

- `docs/choices/first-environment.yaml`: `question`, `asked_by: owner`, `asked_on`, `quote` (S-94's "what
  people/businesses are paying for AI to do now is where we should focus"), `need`, `searched`, `candidates`.
  No `trial`, `verdict` or `pick`.

The `need`, written before looking: (a) support or back-office work with an outcome a script can check;
(b) a permissive licence for code and data; (c) a judged run (7 to 10 paired rounds of base and candidate over
the held-out cases) fits in 1,000 free calls a day, or runs on the local model (Granite 4.0 Micro, about one
second a call); (d) held-out cases the models have not seen, or a way to make them; (e) the world runs in
Podman on this machine with no paid service.

## Leave alone

Everything else. No code, no images pulled, no benchmark cloned into the repository, no component added to the
map, no `DECISIONS.md` row.

## Done when

`docs/choices/first-environment.yaml` parses, has at least five candidates each with the seven facts above or
a stated "not found" for the ones that could not be read, and `scripts/workbench.sh extract substrate:choices`
runs clean. `scripts/check.sh` passes.
