# The framework

What Substrate is, its parts, and how they plug together (S-184 to S-186, 2026-11-23). Every default and its reason
is in `DECISIONS.md`. The framework this replaces (S-125 onward) is `docs/archive/framework-s125.md`: history.

## In one paragraph

**An operating system for AI agents.** Today's agents live in a terminal where everything is a file: one agent, one
context, permissions by convention. Here a working system (a business, a codebase, a household, a game) lives in a
**kernel** where everything is an object: state, actions behind permission gates, events anyone allowed can subscribe
to, and every change recorded. **A top-level orchestrator keeps that system working:** it **maps** it (what the parts
are, what they do, how they connect), **orchestrates** it (sub-agents in shared environments: any harness, any
model, or no model), and **optimises** it (through an optimiser it delegates to, judged before anything changes),
toward goals and values a person sets, asking before anything that matters. It hosts your tools rather than
replacing them: Claude Code or any harness joins unmodified, models come through one gateway, tools through MCP,
environments through OpenEnv, so a change can be rehearsed on a copy before it runs for real.

## The layers

Like GNU on Linux, with Postgres made into the kernel:

| Layer | Is | Defines or does |
| --- | --- | --- |
| **Kernel** ([OpenReplicant/kernel](https://github.com/OpenReplicant/kernel)) | Postgres made into a kernel | The standards: **knowledge** (claims with provenance, review, recall), **interaction** (objects with properties, actions and events; gates `free`, `propose`, `deny`; queues), **authentication** (a login per component, row-level security), **pluggability** (how a component describes itself and plugs in), and the record. Its modules are data transformations and what happens at the Postgres level |
| **Substrate** (this repository) | The orchestrator kit | A little agent framing on the kernel's standards: an ordinary LLM harness given skills, MCP servers and hooks so that it maps, orchestrates and optimises its system. Plus the adapters, the reference stack and this document |
| **Morphogen** ([OpenReplicant/Morphogen](https://github.com/OpenReplicant/Morphogen)) | The optimiser | A sub-agent pluggable into anyone's system: cells (what may change, how it is run, what is better, what must keep passing), optimizers behind a judge they cannot edit, the still-works gate, the system guard, an evidence log |
| **Distributions** (`distributions/` here) | What is built with it | Kinds of environments, multi-stage agents, the assistant, the SMB Foundry or AI ERP; each composed of components. Folders in this repository until Substrate's shape is settled |
| **MetaSoar** ([OpenReplicant/MetaSoar](https://github.com/OpenReplicant/MetaSoar)) | The research | Cognitive architecture: impasse-driven compilation (M-17), System 1 distilled from experience; experiments on OpenEnv |

## The orchestrator

```
 intentions, goals, values ── the person (approves through propose gates)
                │
 ┌──────────────▼───────────────────────────────────────────────┐
 │ the orchestrator: an ordinary LLM harness (Claude Code first)│
 │   skills:  map · catalog · research · orchestrate · optimize │
 │   MCP:     the kernel; Morphogen; what it installs (approved)│
 │   hooks:   gates enforced inside the harness too             │
 │   models:  any, through the gateway                          │
 └──────┬──────────────────────────────┬────────────────────────┘
        │ observes (subscriptions)     │ delegates, adjusts
 ┌──────▼──────────────────────────────▼────────────────────────┐
 │ environments: objects · gated actions · events · the record  │
 │ shared by sub-agents: harness sub-agents, OpenEnv            │
 │ environments, custom MCP components                          │
 └──────────────────────────────────────────────────────────────┘
```

- **Map:** the `map` skill decomposes a system into parts, roles and interfaces, written as Backstage entities (the
  `catalog/` files, read into the kernel, S-176) with evidence.
- **Catalog and research:** for each intended component without a hard dependency, the `catalog` and `research`
  skills fill the catalog with candidates and test them against the need, so the best fit is chosen, not
  remembered.
- **Orchestrate:** the orchestrator watches its system by subscription and delegates work: a quick task to its own
  sub-agents, long or risky work to a separate harness process with its own login, rehearsal to an OpenEnv
  environment in simulation, deterministic work to an MCP component.
- **Optimise:** the `optimize` skill chooses a cell and when to work on it; Morphogen (its Claude Code plugin)
  searches and judges; a winner becomes a proposal the person approves. Who proposes never grades their own work.
- **Error correction and monitoring** are the same loop: observe, notice, delegate or optimise, verify.
- **Autopoiesis:** Substrate's own stack is an environment like any other (its compose file goes into the map and
  back out, S-177), so the orchestrator maintains and grows its own system with the same skills.

## Everything is an object

One kind of thing: an **object** with **properties** (its state), **actions** (messages it accepts, each behind a
gate) and **events** (messages it sends). Everything else is a **trait**, not a type:

| What it used to be called | As an object |
| --- | --- |
| artifact | an object with read and write actions and the trait **versioned** (revisions and provenance) |
| component, agent, handler | an object with the trait **active**: it subscribes and acts on its own |
| environment | an object with the trait **container**: it holds objects, so environments nest |
| stream, source | an object's events; a source is a component that turns a protocol's data into events |
| actuator | an object's action; a gate is a policy on it |
| the blackboard | all objects' properties, in one database |
| a component's view | a query over the objects its login may see |

Objects talk only by messages (pgmq), never by reaching into each other's state, so permissions and the record hold.
Use traits, not inheritance. The Agents & Artifacts model (CArtAgO) is the closest precedent; its words are ours too:
an agent **focuses** on an object to perceive it; observable **state** is replayable, **signals** are transient.
W3C WoT Thing Description 1.1 is the shape of an object's description.

**Rules:** a source runs only while something subscribes to it; starting a new source or handler is a proposal (what
is read is the person's call, docs/privacy.md P1, and so is the cost); large or fast data travels by reference.
**One database:** the kernel's database holds knowledge and the environment's live state together, so one
transaction can change an object and record its version (S-185; the kernel's D-94 (c) to be superseded).

## Slots: every dependency is a contract

| Slot | Contract | Default filler | Could also be |
| --- | --- | --- | --- |
| Environment and delegation | OpenEnv (production and simulation) + MCP; A2A's task states for a delegated task | the kernel's Postgres environment, served as OpenEnv | any OpenEnv environment, any MCP server, a harness sub-agent |
| The map | Backstage entity files, over MCP | the kernel | the plain files in `catalog/` |
| The optimiser | Morphogen's cell contract | Morphogen | anyone's optimiser and judge |
| The harness | skills, MCP servers, hooks | Claude Code | any harness that takes them |
| Models | an OpenAI- or Anthropic-compatible endpoint | Bifrost (`gateway`) | any gateway, a provider directly |

No cycles: the kernel needs only Postgres; Morphogen needs cell files (and reads Backstage when present); Substrate
needs only the contracts; distributions need Substrate and the fillers they choose. The test: Substrate pointed at a
folder of catalog files and one OpenEnv environment still runs.

**Delegation has three kinds of filler,** all on MCP: an **OpenEnv environment** (episodes, rubrics, packaging:
rehearsal and Morphogen's cases), a **harness sub-agent** (Claude Code's own sub-agents for quick work inside the
orchestrator's session; a separate harness process, with its own login, context and record, for long or risky
work), and **custom** (a service, a script, a non-LLM agent). OpenEnv already treats a harness as an environment
(RFC 005), so the line between them is thin.

## OpenEnv, adopted fully (S-184)

Substrate's environments **are** OpenEnv environments: its classes, server, clients, simulation episodes and
rubrics, production mode, harness adapter and packaging, used as they are. What OpenEnv lacks is built inside our
environments, not around them: state in Postgres (so many sessions share one live environment), the database's
logins (OpenEnv's server has no auth: keep it behind ours), approval gates as tool behaviour, events to subscribers.
Simulation `reset` clones a template database, so a change is rehearsed on a copy of the real data: Foundry's
"what-if", with the judge built in. Pinned `openenv` 0.12.0; early development, weekly releases: keep our code
against it thin. A spike proves seven points first (`docs/plan.md`).

## Rules that run through it

- **The cache rule:** an LLM's view of an environment is rendered so it only grows at the end: fixed parts first,
  events in order, volatile parts (the time, the current focus) last; a conversation stays on one model unless
  switching pays for the reprocessing; compaction is rare and in large chunks.
- **Labels are outcomes,** never a decider's own choice; feedback may arrive long after, by the id of what it judges.
- **Gates:** `free`, `propose` (waits for a person), `deny`; enforced by the database, and by hooks inside the
  harness so a sub-agent cannot route around them.
- **Privacy:** `docs/privacy.md`; nothing personal leaves the machine unless a rule is loosened for a named stream.

## What it takes from elsewhere

Agents & Artifacts (focus, state and signals, workspaces); W3C WoT (an object's description); Palantir Foundry's
Ontology (object types, links, actions validated, permissioned and audited, what-if); BDI's discipline (a typed
vocabulary, a validator, retraction on failure) as tables and gate checks, not a BDI runtime; OpenEnv; MCP; A2A's
task states; CloudEvents for event envelopes; Home Assistant's stable ids; PostgREST and pgmq as parts. The research
behind this: `docs/research/Object environments prior art.md`.

## What looks new

As far as the research searched: trait-based objects whose actions sit behind free, propose and deny gates in one
Postgres that is blackboard, bus, auth and record; unmodified harnesses joining through the model endpoint; an
optimiser whose judge the optimizer cannot edit, wired to the map; and (MetaSoar's) a System 1 distilled from the
record that makes the system cheaper as it learns.
