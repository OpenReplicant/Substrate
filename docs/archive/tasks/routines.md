# Task: the first judged comparison: one model against the same model with routines below it

**Parked by S-111 (2026-11-16):** papers first. Steps 1 and 2 are done (S-109, S-110); the routine handler and
learner sit uncommitted in the worktree `.claude/worktrees/agent-a0f4cd1e115a58fdd`. Resume, change or drop
after the catalog's first reading, which is on this question.

**Model:** the largest for the design and the two judge checks, Opus to build. **Needs:** `first-package.md`,
`meter-factors.md`, `verdict-fields.md`. S-102 and S-103: this is the dual-process idea as an experiment.

## The question

On `lookups`, with the model held fixed: does an agent whose repeated steps are taken by routines cost less
(calls, tokens, time) with no fall in the outcome, on cases neither side has seen?

## Scope

1. **The judge can see, first** (`docs/contracts/verdict.md`): the baseline against itself must not pass; a
   deliberately worse agent (a lower step limit, or a prompt with the registries removed) must be refused.
   Nothing below is run until both read as expected.
2. **A routine, simplest kind**: a rule handler that answers a step when the observation matches a pattern
   (the question's shape, the last action, a field present in a result) and gives the action that followed
   it before. No generated code. It escalates on anything else, so the model still takes what is new.
3. **Who builds them.** Not the small model. Between episodes, from the call record of `dev` and live
   episodes only: first a script (steps the model answered the same way N times), and as a second arm a
   dearer rank reading the record (a larger model through the gateway, or a Claude Code session). Each set of
   routines is a candidate through `propose_handler`: it runs nowhere until a verdict and approval.
4. **Where to hand up.** When a step escalates, which dearer handler takes it is `select`'s job. Built here:
   cost order. Recorded for later, not built: choosing by what each handler has been measured good at on
   this kind of task (the owner's "rank/task/association").
5. **One comparison, judged once**, recorded pass or fail with its verdict, and what the routines took
   (share of steps, by shape).

## Claude Code as a rank

A session can be a handler above the local model. Pointed at the gateway by endpoint and model name, its
calls are metered like any model's and it may sit in a judged run. On the owner's subscription its calls do
not pass the gateway, so there it builds and advises between episodes and is not a rank in a judged run.
Read Claude Code's current docs for the endpoint settings before wiring either (rule 1).

## Leave alone

`repos/morphogen` (a judge change goes upstream, red team first). Held-out cases. Routines that are code a
model wrote, and selection by condition or strength: later entries in the search space.

## Done when

The two checks read as expected; one candidate set of routines has a verdict; the result and the cost
factors are in the Knowledge Kernel; `scripts/test.sh` and `scripts/check.sh` pass.
