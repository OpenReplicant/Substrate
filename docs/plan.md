# Plan

The one current plan (S-124, 2026-11-17). It replaces the plans in `docs/archive/` (the spec and its build plan,
the experiment-first direction, the handoff, the task briefs); those are kept as history and are not to be worked
from. Every default and its reason is still in `DECISIONS.md`.

## What Substrate is now

An agent framework. You build an agent for a system you need, run it, and watch and change it in Workbench,
which is Substrate's web UI and store. Morphogen stays a part you can use as it is; no more work goes into it
for now.

## What already exists

- **Packages** (`packages/`): an environment (what the agent senses and may do, and how its outcome is
  measured) and the agent configured for it, started by naming it in `PACKAGES`. `lookups` and `papers` are the
  two so far.
- **The model gateway** (Bifrost): every model call goes through it with its caller's key and is recorded.
- **Workbench** (`workbench/`): typed items with claims beside every value, a web shell, an API, extractors, live
  events, and an MCP server for Claude Code.
- **The map, the observer and interviews** (`plugins/substrate/`, the `interview` skill): what a system is,
  what runs, and what the people who own it say about it.

## Steps

| # | Step | Done when |
| --- | --- | --- |
| 1 | Get the stack up on the machine you work on (`setup` skill) | `scripts/check.sh` passes |
| 2 | The owner picks the first real system to build an agent for | the pick is a row in `DECISIONS.md` |
| 3 | Build that agent as a package, using what exists | it does the job end to end on real input, every model call recorded at the gateway |
| 4 | Run and watch it from Workbench: its episodes, its calls and cost, its hand-offs in the review lane | the owner can start it and see what it did without a terminal; only the views it needed were added |
| 5 | Write down the path that worked (new package → run → watch → change) in `packages/README.md`, then build a second agent by following it | the second agent needed no new framework code, or the framework changes it needed are named |

Workbench is no longer frozen: add what steps 3 to 5 need, and nothing they don't.

## Deferred

Morphogen R&D (statistics, the judge's own gateway and meter, the queue, GitHub Actions, the evidence log), the
case-and-scorer kit and the environment contract's generalisation, held-out cases by script, the paper catalog's
publication and reproductions, the hosted mapper and hosted judging, the personal assistant, the slot model
(`docs/archive/slots.md`).

## The owner's to decide

- The first system (step 2).
- Rotating the Postgres password; putting the Gemma model at the gateway.
- The licence and whether the repository goes public.
