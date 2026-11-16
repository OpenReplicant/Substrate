# Handoff: what this project is, what to do next, and how to work on it

Written 2026-11-16 by the session that built the paper catalog and reviewed Morphogen, for a session on
another model that did not see that conversation. It wins over `docs/tasks/README.md` and `docs/direction.md`
where they disagree. Decisions behind it: S-111 to S-118 in `DECISIONS.md`.

## The project in one line

**An agent harness where every component can be swapped, and every swap is judged on cases the changer
cannot see.** Others offer the swapping. The judging is what they do not, so it leads.

The owner's wider idea, which this is the first instance of: a map that decomposes a system into parts,
interfaces and cited evidence can explain the composition of anything, and a mind that works from such maps
can manage and improve systems, its own included. The aim is a position from which companies hire the owner
to implement and manage their systems. The owner needs income and public notice soon.

## One job per repository

Two projects, not three (S-120): Morphogen, and Substrate with Workbench as its store and GUI.

| Repository | Job | State |
| --- | --- | --- |
| Morphogen (`repos/morphogen`, its own repo) | The judge. The product that is led with | Works; six faults to fix first (below) |
| Substrate (this repo) | The harness, its slots, and packages | Frozen except for what the plan below needs |
| Workbench (`workbench/`, part of Substrate) | Substrate's store and GUI, and the catalog's home: claims are evidence, ontologies name slot types, embeddings are lookup, cron and messages run the harvest and queue | Frozen: use it as it is, add no features |

## What exists and works

- `packages/lookups`: a small environment with one model handler; used to check that the judge can tell same
  from worse (S-110). Its cases are too few (48) to see small effects.
- `packages/papers`: 9,466 papers on agent components from 37 listings, with citations, and 1,108 flagged
  `testable` (code with a usable licence). Lookup by need works: `scripts/workbench.sh run
  packages/papers/lookup.py "NEED" [--testable --limit N]`. The per-paper records (kind, slot, claimed result)
  are NOT reliable: a 3B model read them at the floor (S-115, S-116).
- Morphogen pull requests 81, 82 (item 1.3, S-119) and 83 (the intake for item 1.1b, S-121, S-122) are merged. The
  judge user `morphogen-judge` exists; `scripts/judge-user.sh` sets up its side and is the owner's to run.

## What is stopped

The build plan (`docs/build.yaml`, paused), routines (`docs/tasks/routines.md`, parked in a worktree), new
Workbench features, the map of Substrate itself, the reading agent on small models, and models under 12B as
an agent or reader (embeddings excepted). The owner's local model is a Gemma 4 26B; it is not yet at the
gateway.

## The plan, in order

Every week ships something public or billable. Nothing is built that does not serve that.

1. **Morphogen, fit to show** (in its own repository, by pull request, red team first; each judge change
   needs the owner's yes):
   1. *Run the judge where the changer cannot reach.* On one machine the agent can read the private cases.
      Two ways, both wanted: (a) a GitHub Actions workflow taken from the base branch, with private cases in
      a separate private repository read through a secret, for projects whose model calls can go to a hosted
      endpoint; (b) on the owner's machine, a second Unix user that owns the private cases and runs the judge
      (as a self-hosted runner or a small service), so the local GPU is usable and file permissions do the
      isolating. A container alone does not do it: the agent's user can start containers. A self-hosted
      runner must not serve a public repository's pull requests.
   2. *Statistics for agent quality.* Today a whole run is one sample (sign test over rounds, p at most
      0.01, more rounds while undecided). Add case-by-case pairing for scored outcomes, state the smallest
      effect the case set can detect before running, and correct or drop the extend-while-undecided rule.
      Then the same-against-same check on many more than 12 trials.
   3. *Refuse a run whose scorer saw fewer cases than expected* (the fault S-110 found).
   4. *Count how often a private set has been judged against*, and warn when it is stale.
   5. *Anchor the evidence log* outside the machine (publish or sign the head hash).
   6. *A ten-line quickstart for "an agent, an eval set, is this pull request better", and a verdict report
      a customer can read.* Present optimizers, the UI and Backstage reading as extras.
2. **The write-up**: what the judge caught here (two "worse" agents that were not, the lost case in every
   run), from the verdict log. No new code.
3. **The catalog, public**: a static export with search, and the figure that about 12% of the papers name a
   repository with a usable licence (a lower bound: only repositories named in the abstract are counted).
   Needs the owner's yes to publish.
4. **Held-out cases by script**: hundreds of lookup cases generated from the registries with a seed kept
   where the agent cannot read it (item 1.1's second user).
5. **One reproduction**: a well-known component with code (Agent Workflow Memory, arXiv 2409.07429, is in
   the catalog) on the owner's Gemma model, judged against a plain baseline, on a task the owner names.
   Record the smallest model at which it works (S-113).
6. **The first audit** for a friendly team: their recent changes, held-out cases and the judge in their
   pipeline, a report saying which changes helped.
7. Only then: slots (an interface with a contract test), plug-ins (admitted when they pass the test, trusted
   when they have a verdict), configurations, and re-reading the abstracts with a capable model.

Stop rule: if three reproductions give nothing the judge can separate from noise, stop and rethink.

## Who does what

| Work | Model |
| --- | --- |
| Design of a judge change, review before merge, the write-ups | The main session (Opus if the largest is unavailable) |
| Building a briefed change, tests, the static export | Sonnet subagent |
| Lookups, page fetches, file sweeps | Haiku subagent |

## How to work here without wasting the owner's usage

- One brief, one agent, one report. A cold subagent costs 250,000 to 350,000 tokens: give it a complete brief
  and continue the same agent for follow-ups.
- Write a decision row only for a decision. Do not write briefs for work that fits in one sitting.
- Measure before building around an assumption (a reading model was built around a 3B model that could not
  read).
- Never print process command lines (`ps` args): scripts here pass secrets as arguments. Pids and names only.
- Never touch the owner's own programs on the GPU. If a local model will not load, say so.
- Commit only when the owner says, on `direction/experiment-first`, gitleaks first. Nothing is pushed.

## The owner's to decide

Which Morphogen fixes to make and in what order; whether the catalog and this repository go public, and the
licence; the name the work is published under; the task for the first reproduction; who the first audit is
for and the price; rotating the Postgres password (part of it was printed in a
session); whether to put the Gemma model at the gateway.
