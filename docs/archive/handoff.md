# Handoff: what this project is, what to do next, and how to work on it

Written 2026-11-16 by the session that built the paper catalog and reviewed Morphogen, for a session on
another model that did not see that conversation. It wins over `docs/tasks/README.md` and `docs/direction.md`
where they disagree. Decisions behind it: S-111 to S-118 in `DECISIONS.md`.

## Where it stands (end of 2026-11-16, second session; read this first)

Decisions S-119 to S-123 are in `DECISIONS.md`. Committed through `8c13016`; nothing is pushed. S-123 is the
positioning: several ways in (mapping, process and automation consulting, new agents, judging changes,
self-optimization) on one spine, map, cases and scorer, deploy, judge, optimize; self-host first, then a hosted
mapper for public repositories, hosted judging later.

**Done**
- Morphogen pull requests 81, 82 and 83 are merged (`b57fbbb`, pinned in `repos.yaml`). 82 is item 1.3 below. 83 is
  the intake for item 1.1b: `morphogen intake judge NAME` takes a candidate as a git bundle on standard input and
  judges it by a request the judge's side keeps; `morphogen intake advance NAME` moves the judge's base forward.
- The judge user `morphogen-judge` exists (home `/var/lib/morphogen-judge`, mode 700, linger on, rootless Podman
  works). The owner ran `scripts/judge-user.sh install`, `clone`, `door`, `images`, `request` and `give`. Its side
  has Morphogen, a clone of this repository, the request `lookups-rehearsal`, the rehearsal cases (not held out)
  and the tools and database images.
- The door works: `git bundle create - CANDIDATE ^direction/experiment-first | sudo -n -u morphogen-judge
  /usr/local/bin/morphogen-intake lookups-rehearsal` reaches the judge's own install, request and clone. The sudo
  rule refused a path, a second argument and another command.
- Two projects, not three (S-120): Workbench is Substrate's store and GUI.
- `docs/writeups/what-the-judge-caught.md`: item 2 below, drafted, not published.
- `docs/slots.md`: the owner's model of the harness (slots, roles, fillers with slots of their own, encoders,
  processors and decoders inside memory). Thinking, not a build plan.

**Not committed** (the owner has not said to): `docs/slots.md`, this section, the source `agent-memory-atlas` and
its export in `catalog-info.yaml`, `deploy/judge/requests/lookups-rehearsal.yaml`, and the `request` and `give`
verbs in `scripts/judge-user.sh`. `scripts/check.sh` passes. Scan with `bin/gitleaks protect --staged --redact`;
commits are authored `Claude <noreply@anthropic.com>` through `GIT_AUTHOR_*` and `GIT_COMMITTER_*` (no git
identity is configured).

**Next, in order**
0. *The case-and-scorer kit* (S-123), first because every way in needs it and most teams have no evals. Two
   halves: an existing eval into the environment contract (`docs/contracts/environment.md`), with its scorer outside
   the agent and printing `cases_seen`/`cases_expected`; and a process's history (a CSV of tickets, logs, past
   decisions) into a case set whose recorded outcomes are the answers, split so a held-out part goes to the judge
   user (`scripts/judge-user.sh give`). Rehearse it on the lookups cases and on one process-history set; its check
   is `scripts/contract.sh environment` passing on what it makes. Item 3 below (held-out cases by script) folds
   into it. Also in it (`docs/slots.md`, "The environment's own slots"):
   - *A scorer contract:* a scorer is admitted when the do-nothing and constant agents score its stated floors,
     the dev answers replayed score 1, it agrees with a person's labels on a small calibration set, and the
     red-team cheats fail against it. A panel of scorers needs its verdict rule (which metric decides, which only
     bound) fixed before the run. Generated scorers are written on the judge's side and reach the base only by
     the owner's advance. The kit ships a library of reusable scorers as catalog entries.
   - *Three wraps of different shapes* to test whether the contract is universal: a coding task with tests (the
     observed stepping mode: the environment's actions as an MCP server, gated by the agent's hooks), a support
     task with a simulated customer (a rubric scorer), and a process-history set (a state machine, late outcomes).
     Where the contract bends, it changes. Put the contract's five rules at the top of
     `docs/contracts/environment.md` first: people own the environment and scorer, the candidate only the agent;
     episodes by `reset`/`step` or one call for a black-box agent; actions declared and gated; scored outside the
     agent on held-out cases with stated floors; what is read from outside is recorded and replayed.
1. *The judge's own gateway and meter.* The door stops here: the judge answered "the cell measures
   metered.tokens ... but no gateway is named". Today's gateway runs in the author's Podman and its meter is a
   script in this repository, so both must exist on the judge's side (its own Bifrost container, its own keys, a
   meter it holds), named in the request's `local.gateway`. Ollama must be reachable from it.
2. *A queue as the second carrier* (S-122): a worker run by the judge user as a systemd user service, reading
   requests from pgmq in Workbench and posting verdicts; it lives here, not in Morphogen. Advancing the base never
   goes on the queue. A verdict on the queue is a copy; the judge's evidence log is the proof.
3. *Held-out cases by script* (item 4 below), made under the judge user, with connected questions among them.
4. *Statistics* (item 1.2 below) before the write-up is published.
5. Then items 1.4, 1.5 and 1.6 below, and GitHub Actions (1.1a) as the same interface a third time.

**Asked of the owner and not answered**
- Record pages plus a typed graph over claims as the default memory design, as a hypothesis to be judged
  (`docs/slots.md`, last part of the encoders section)? Its backing is one vendor's own test.
- Make the first public demonstration "GEPA's `optimize_anything` on an agent part, then judged on cases it never
  saw", ahead of item 5 below? Recommended. Morphogen already drives `optimize_anything` (`optimize.py`, `Gepa`).
- A note in the verdict when a scorer prints no case counts (a small Morphogen pull request)?
- Score Workbench against the Agent Memory Atlas's seven marks?
- Still open from before: rotate the Postgres password; put the Gemma model at the gateway.
- From S-123: the open core's licence (permissive or AGPL-like; it matters once there is a hosted service);
  consulting or the platform as the main business (it decides the front page); pricing; the first customer.
- After the kit, in S-123's order: the self-host quickstart (1.6), a hosted mapper for public repositories only, one
  public write-up and one public audit, hosted judging when someone asks to pay for it.

**Working notes**
- `sudo` needs the owner's own terminal: the `!` prefix has no terminal for a password. Put sudo steps in
  `scripts/judge-user.sh` and ask for the output to be pasted.
- Morphogen's whole suite in Podman takes about 12 minutes: run it in the background.
- Opinion given to the owner: Morphogen's own optimizers, web UI and Backstage reading are where it is over-built;
  the judge, requests, the intake and the evidence log are the product.

## Four ideas, two repositories (owner, 2026-11-16)

| Idea | Where | State |
| --- | --- | --- |
| Agent environments: sensors, gated actions, episodes, scorers in people's custody | Substrate (`docs/contracts/environment.md`, `packages/`) | one built (lookups); three wraps next |
| A knowledge store: cited claims, modular encoders, processors and decoders | Substrate (`workbench/`) | built; the modules are the open part |
| Judged change and optimization: nothing lands without a verdict the changer cannot reach | Morphogen | built; the product; faults 1.2 to 1.6 left |
| Everything as a component graph (slots, fillers, the map) | Substrate (the map, `docs/slots.md`) | useful and transferable so far, not shown to be better than doing without |

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
