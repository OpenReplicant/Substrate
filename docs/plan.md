# Plan

The one current plan (S-124, 2026-11-17). It replaces the plans in `docs/archive/` (the spec and its build plan,
the experiment-first direction, the handoff, the task briefs); those are kept as history and are not to be worked
from. Every default and its reason is still in `DECISIONS.md`.

## What Substrate is now

An agent framework. You put an environment on a system you need, run it, and watch and change it in Workbench,
which is Substrate's web UI and store. Its shape is `docs/framework.md` (S-125): the environment is data in
Postgres, pass-through to Claude Code is the default, components distilled from the record carry cards, a judge
tests them on cases their author never saw, and environments nest. Morphogen stays a part you can use as it is;
no more work goes into it for now.

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
| 2 | Read the three closest works in full (Global Workspace Agents, CogRec, Graphiti's data model) and the current Claude Code channels docs; amend `docs/framework.md` where they change it | the page cites what was read and what changed (done 2026-11-17, S-129; checking the claim fields against Workbench's schema waits for step 1) |
| 3 | The owner picks the first real system: one with a steady stream of similar work and a checkable outcome | the pick is a row in `DECISIONS.md` |
| 4 | Pass-through on it: its streams into pgmq topics, readings into the claim log, a Claude Code channel subscribed, one actuator gated at `propose` | it does the job end to end on real input; every event, model call and action is in the record; the owner decides proposals in Workbench |
| 5 | One distilled component with its card, and the judge interface's first filler (a script as the judge user, the held-out slice of the record) | a verdict on the component against pass-through; promoted or refused on it |
| 6 | Write down the path that worked, then put a second environment on another system by following it | the second needed no new framework code, or the changes it needed are named |

Nesting, self-levers and the other layers in `docs/framework.md` come after step 6, each tested against
pass-through. Workbench is no longer frozen: add what these steps need, and nothing they don't.

## Deferred

Morphogen R&D (statistics, the judge's own gateway and meter, the queue, GitHub Actions, the evidence log), the
case-and-scorer kit and the environment contract's generalisation, held-out cases by script, the paper catalog's
publication and reproductions, the hosted mapper and hosted judging, the personal assistant, the slot model
(`docs/archive/slots.md`).

## The owner's to decide

- The first system (step 3).
- Rotating the Postgres password; putting the Gemma model at the gateway.
- The licence and whether the repository goes public.
