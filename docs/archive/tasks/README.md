# Handoff: who does what, and in what order

Written 2026-11-15 for sessions that did not see the conversation behind S-94. Read `docs/direction.md` first.
Work happens on the branch `direction/experiment-first` and merges to `main` at a milestone, after
`scripts/check.sh` passes on the owner's machine. Changes to Morphogen and to the kernel repository go to those
repositories by branch and pull request (the `upstream` skill).

**Read [`../handoff.md`](../handoff.md) first (S-118, 2026-11-16).** It says what the project is, what is
stopped, and the plan in order; it wins over this file where they disagree.

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

## Now (S-97 to S-102, 2026-11-15): start here

The owner's direction, in order of when it was said: testing stays small, with one cheap local model held
fixed (S-97); the first thing to have is a useful starter agent whose components optimize themselves on the
tasks it is given (S-98), research first (S-99; Granite 4.0 Micro picked, S-100); and (S-101) an
**environment** is the unit that is configured, started and shared, there is **one way to start** (no script
per mode), the first environment is **papers** (read, then reproduce: the early goal with provable outcomes),
and the agent **works on its own code** with other projects' tools interfaced. Then (S-102) the words were
fixed: an **environment** is what is sensed and may be done, an **agent** is a route of handlers that can be
a single one with or without a model, and a **package** (`packages/<slug>/`) holds both and is what is
started and shared; where a brief below says "environment" for the directory, read "package". The order:

Order changed by S-103: one package end to end before anything general, and the first judged comparison on
work that repeats.

Order changed again by S-111 (2026-11-16): papers first. [`paper-catalog.md`](paper-catalog.md) (largest for
the design, Sonnet to build) is the task to take now: a catalog of published work on agent harnesses and
cognitive designs, amassed with no model and presented, with a queue of what is cheap to test. Item 2 below
then reads from that queue and item 4's stage B reproduces. Item 1b is **parked**, with its routine handler
in a worktree (S-109). Item 1 is done.

Then (S-114, 2026-11-16): the catalog is built (S-112) and the task now is [`rd-pipeline.md`](rd-pipeline.md):
a fixed record per paper read from its abstract, lookup by meaning, a queue, then reproduce and judge. It
replaces stage A of item 2; stage B stands as its last step. Which model an experiment uses is open (S-113).

1. [`first-package.md`](first-package.md) (Opus): `packages/lookups`, one model handler, tools as actions, the
   step loop in its smallest form, one start.
1b. [`routines.md`](routines.md) (largest for the design and the judge checks, then Opus): the model alone
   against the model with routines below it. Needs 1 and item 4's two briefs.
2. [`papers-environment.md`](papers-environment.md) stage A, reading (Opus); needs 1, can run beside 1b.
3. [`codebase-environment.md`](codebase-environment.md) (Sonnet for the tool search, Opus to build); can run
   beside 2.
4. [`meter-factors.md`](meter-factors.md) and [`verdict-fields.md`](verdict-fields.md), then
   [`papers-environment.md`](papers-environment.md) stage B, reproducing (largest for the design and the two
   judge checks).
5. What a newcomer hits (`docs/readiness.md`): [`fresh-clone.md`](fresh-clone.md), then
   [`first-read-docs.md`](first-read-docs.md) with [`04-rename-pass.md`](04-rename-pass.md), then
   [`spec-rewrite.md`](spec-rewrite.md). [`observed-ontology.md`](observed-ontology.md) when a map needs it.
6. Waiting: [`self-approval.md`](self-approval.md) (the owner's yes, and before stage B's gate is used);
   [`judging-another-system.md`](judging-another-system.md), [`second-checkout.md`](second-checkout.md)
   (until someone has a system they want better); [`05-pick-and-judge-design.md`](05-pick-and-judge-design.md),
   [`later-packaging.md`](later-packaging.md) (the general loader, Substrate's own streams as a package,
   `state.yaml`: when a second package exists);
   [`06-environment-and-baseline.md`](06-environment-and-baseline.md) (a benchmark is one more environment,
   if a public comparison is wanted). [`starter-agent.md`](starter-agent.md) stage 1 is done; its last
   section says what carries the rest. [`client-readiness.md`](client-readiness.md) is done as far as useful.

State on 2026-11-16: committed through `96c0a2e` (S-108 to S-110). No git identity is configured; commits
use `Claude <noreply@anthropic.com>`.

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
