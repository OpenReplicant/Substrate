# Handoff: who does what, and in what order

Written 2026-11-15 for sessions that did not see the conversation behind S-94. Read `docs/direction.md` first.
Work happens on the branch `direction/experiment-first` and merges to `main` at a milestone, after
`scripts/check.sh` passes on the owner's machine. Changes to Morphogen and to the kernel repository go to those
repositories by branch and pull request (the `upstream` skill).

## Which model does what

The owner's use of the largest model is limited, so it is kept for work where a wrong call is expensive.

| Work | Model |
| --- | --- |
| Contracts between the three repositories (cell, verdict, environment, workflow); the experiment design; anything touching Morphogen's judge core; task briefs; review before a merge to `main` | the largest model available |
| Refactors that keep behaviour (optimizers out of Morphogen into plugins; Workbench out to the kernel repository); wiring the first environment and the plain-agent baseline; rewriting `docs/spec.md` around `docs/direction.md` | Opus |
| The rename pass; benchmark licence, upkeep and run-cost checks, recorded through the `research` skill | Sonnet |

## Order

1. **Contracts** (largest model): one page each in `docs/contracts/` for the cell format, the verdict, the
   environment interface (reset, step, outcome measure, held-out cases) and the workflow field. Start from what
   exists: `morphogen.yaml`, Morphogen's `BRIEF.md` cell table, `plugins/handlers/ladder.py`, spec section 10.
2. **Briefs** (largest model): one file per task in this folder, each with scope, files to touch, what to leave
   alone, and the check that proves it done.
3. **Benchmark checks** (Sonnet): for each benchmark shortlisted in `docs/direction.md`, its licence, last
   release, how a run is scored, and model calls per task. Write the need and candidates to
   `docs/choices/first-environment.yaml`. Do not pick.
4. **Rename pass** (Sonnet), from the glossary below, with no change in behaviour; every test suite passes.
5. **Step 1 pick and step 3 design** (largest model), once 3 is back: the budget arithmetic (calls per judged
   run against 1,000 free calls a day and what the local model carries), the pick, and the two checks that show
   the judge can see (a candidate against itself; a deliberately worse one against it).
6. **Environment and baseline** (Opus), against the environment contract.
7. **Review and merge** (largest model, then the owner).

## Now (S-97, 2026-11-15)

The owner, after items 1 to 3: testing stays small for now; the framework is first made fit for someone else
to pick up and for a first client system (mapping, then optimizations). What is tested is the agent around a
model, never the model: each environment holds one cheap, minimum-viable model fixed and looks for a baseline
and a difference. So the order from here is:

1. [`client-readiness.md`](client-readiness.md): three walks (a newcomer, a second system, an optimization on
   paper) and the list of what stops them.
2. [`04-rename-pass.md`](04-rename-pass.md), then [`spec-rewrite.md`](spec-rewrite.md) and the `README.md`,
   so what a newcomer reads matches what is there.
3. The briefs cut from the readiness findings (walk 1 is done, `docs/readiness.md`: 19 findings, 5 that stop
   someone, and 6 real limits on judging another system): [`fresh-clone.md`](fresh-clone.md) (Opus),
   [`first-read-docs.md`](first-read-docs.md) (Sonnet, with the rename), [`second-checkout.md`](second-checkout.md)
   (Opus), and [`judging-another-system.md`](judging-another-system.md) (largest, then Opus; after walk 2).
   [`self-approval.md`](self-approval.md) once the owner says yes.
4. The environment work (05, `meter-factors.md`, `verdict-fields.md`, 06), kept small: one environment, one
   local model, the two judge checks, one comparison.

## Briefs

Items 1 (`docs/contracts/`, S-95), 2 (these files) and 3 (`docs/choices/first-environment.yaml`) are done. Each brief has its scope, the files to touch,
what to leave alone and the check that proves it done. A session takes one brief.

| Brief | Model | Needs | Can start |
| --- | --- | --- | --- |
| [`client-readiness.md`](client-readiness.md) | Opus, then largest | the owner, for one walk | now: first |
| [`03-benchmark-checks.md`](03-benchmark-checks.md) | Sonnet | nothing | done |
| [`04-rename-pass.md`](04-rename-pass.md) | Sonnet | nothing | now |
| [`meter-factors.md`](meter-factors.md) | Opus | nothing | now; before task 6's first judged run |
| [`verdict-fields.md`](verdict-fields.md) | Sonnet | nothing | now; before direction step 3 |
| [`self-approval.md`](self-approval.md) | Opus | the owner's yes | before any agent login decides |
| [`05-pick-and-judge-design.md`](05-pick-and-judge-design.md) | largest | 03, the owner's go-ahead to run a benchmark | budget arithmetic done; the trial waits |
| [`06-environment-and-baseline.md`](06-environment-and-baseline.md) | Opus | 05, meter-factors | after 05 |
| [`07-review-and-merge.md`](07-review-and-merge.md) | largest, then the owner | the milestone's tasks | at each milestone |
| [`spec-rewrite.md`](spec-rewrite.md) | Opus | 04, 06 | after 06 |

Tasks 04, `verdict-fields.md` and `self-approval.md` touch different files and can run side by side; 04 and
`spec-rewrite.md` cannot. Not briefed, because the backlog rule says not yet: optimizers out of Morphogen into
plugins, and Workbench out to the kernel repository.

## Glossary for the rename

| Today | Becomes |
| --- | --- |
| Workbench, kernel | Knowledge Kernel (code paths change only when it moves to the kernel repository) |
| the ladder, the handlers ladder | the fallback learner |
| vocabulary (one thing) | taxonomy (SKOS) and ontology (OWL) |
| term | concept in a taxonomy; class or property in an ontology |
| review lane | moderation queue |
| approval policy | workflow |
| cell (Morphogen's word) | governed component, on Substrate's side; Morphogen keeps "cell" |
| map and model, used for the same thing | map |
| drift | gap |

## Rules that hold throughout

- Morphogen is the floor: never weaken a check, read held-out cases or change the judge's rules from a change
  being judged. Its own `CLAUDE.md` requires a red-team test before a judge change.
- The backlog in `docs/direction.md` is built when an experiment needs it, not before.
- Decisions are new rows in `DECISIONS.md`. Ask the owner only for decisions that are theirs.
