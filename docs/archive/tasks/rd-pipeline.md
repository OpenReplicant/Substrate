# Task: the R&D pipeline: from a need to a judged result

**Model:** the largest for this design and the review; Sonnet to build; the reading itself is done by a small
model through the gateway. **Needs:** `paper-catalog.md` (done, S-112). **Decided by:** S-114. Replaces stage A
of `papers-environment.md` (every stated claim of a whole paper) with a fixed record per paper; stage B
(reproducing) stands and is this pipeline's last step.

## The pipeline

| Step | What happens | Model | State |
| --- | --- | --- | --- |
| 1. Harvest | lists, saved searches, metadata, citations, `testable` | none | built; started by hand |
| 2. Vectors | one per paper from its title, abstract and record | the embedding model | Workbench's recall, already there |
| 3. Record | the fixed fields below, read from the abstract | small, local first | this brief |
| 4. Lookup | "a component that does X": recall over papers, filtered by kind, slot, `testable` | none at query time | this brief |
| 5. Pick | the papers to try, into a queue with the reason | a person, or an agent proposing | this brief (the queue) |
| 6. Full read | the method in enough detail to build, only for picked papers | larger | later |
| 7. Reproduce | the method as a candidate in a package, judged against the baseline | S-113: smallest first | `papers-environment.md` stage B |
| 8. Result | replicated or not, at which model, back on the paper | none | with 7 |

## The record (step 3)

Fields on `paper`, each a claim whose quote is found word for word in the abstract (code checks this and
refuses a field whose quote is not there; a field the abstract does not support stays empty):

- `component_kind`: one of memory, planning, tool-use, reflection, skill-library, routing, multi-agent,
  self-improvement, evaluation, world-model, prompt-optimization, benchmark, survey, other. The list starts
  from the headings the curated lists already use and can grow by a decision.
- `slot`: where it would plug in here: handler, route, notes, sensor, learner (between episodes), outcome
  (how a run is scored), none.
- `does`: one sentence, what the component does, for lookup.
- `result`: the headline claim: metric, value, benchmark, compared with what.
- `needs`: the model or models named, and anything else stated (training, data, hardware).
- `record_by`: the model that read it, and when.

## How it is built

- The package gets its environment and agent (`environment.yaml`, `agent.yaml`, a driver and a scorer, as
  `lookups` has): an input is a paper's abstract, the one action is `record`, and the gate is the quote check.
  One model handler, the model named in `agent.yaml` and called through the gateway.
- **Dev cases:** 40 abstracts with the record a dearer model wrote and a person can correct, in the
  repository, marked as model-written. Score: per field, agreement on `component_kind` and `slot`; for
  `result` and `needs`, whether the quoted span overlaps the reference's. Floors: an agent that records
  nothing, and one that always says `other`/`none`. Held-out cases are the operator's, as for `lookups`.
- **Run:** the record pass takes `testable` papers first, most-listed first, a limit per run, resumes, and
  never reads a paper twice with the same model and prompt.
- **Lookup:** recall limited to papers (a type filter if recall lacks one), with filters for kind, slot and
  `testable`; from the command line and in the Papers view.
- **Queue:** a `trial` field on `paper`: `queued`, `running`, `replicated`, `not replicated`, `dropped`,
  with who set it and why; the view filters on it.

## Leave alone

`repos/morphogen`; `packages/lookups`; the owner's own programs on the GPU (if a local model will not load
for lack of memory, stop and say so, or use a free model at the gateway for the trial and say which).

## Done when

- The contract test passes for the package's environment (`scripts/contract.sh environment papers`).
- The dev score is printed for the default model, with both floors.
- 200 testable papers carry a record, every field opening to its quote in the abstract.
- A lookup for a described need returns papers with their kind, slot and `testable`, and one paper can be
  queued from the view.
- `scripts/check.sh` passes.
