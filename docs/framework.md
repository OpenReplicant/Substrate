# The framework

What Substrate is, what it is made of, and how the projects plug together (S-209 to S-214, 2026-11-24). Every
default and its reason is in `DECISIONS.md`. The shape this replaces (S-185: "an operating system for AI agents",
objects and traits, the orchestrator) is `docs/archive/framework-s185.md`, kept as history. Its ideas about objects,
gates and OpenEnv still hold where they sit now: in the kernel and in Substrate's optional parts.

## In one paragraph

Two products and a distribution. **Morphogen** maps a system, researches and catalogues the options for each of its
parts, and optimises it behind a judge the optimiser cannot edit, all in plain files on whatever harness the user
picks. **The kernel** is Postgres made into a kernel: knowledge with provenance, review, logins, the record, a
module contract and a desktop. It ingests Morphogen's files when someone wants search and graph traversal.
**Substrate** is the default distribution: an agent harness set up to use both, interactively, with the optional
parts that let agents act in a live system under gates installed onto the kernel. **MetaSoar** is the research,
first of all System 1 skills. Our agents and experiments are built on the distribution.

## The projects

| Project | Is | Needs |
| --- | --- | --- |
| **Morphogen** | the kit: map, research, catalog, optimise; the judge at its core | files: a Backstage catalog and the operator's private file; any harness that takes Agent Skills and MCP |
| **Kernel** | Postgres made into a kernel; its core is what every kernel user needs (knowledge, review, authentication, the module contract, the record), and its desktop | Postgres |
| **Substrate** | the default distribution: configuration, its optional parts, the stack | the kernel, Morphogen's plugin, a harness, a model endpoint, all through their contracts |
| **MetaSoar** | the research: cognitive architecture, System 1 skills | OpenEnv for experiments; Morphogen to judge |

No cycles. Morphogen needs no kernel, the kernel needs no Morphogen, and Substrate needs both only through their
contracts.

## Morphogen: the kit (S-209)

- **Map:** interview a person, work through a hypothetical design, find facts through whatever the harness can
  reach; build the map out step by step and detail the parts that matter.
- **Research and catalog:** for each role a part plays, search openly for options and document each one with its
  interfaces and adjustable parameters, or at least a link to its docs once it is chosen. Documentation is fetched
  into markdown files by a docs MCP server (to be picked with the `research` skill).
- **Optimise:** cells say what may change, how it is run and measured, and which tests must keep passing. The
  selector chooses scope, optimiser and measure; adapters hand a cell to GEPA, Optuna, OpenEvolve, AFlow or a
  Claude Code worker. The judge decides on cases the optimiser never saw.
- **Orchestrate:** nothing to build. The harness does it, given MCP servers for access.

**One format:** every committed artifact is a Backstage catalog entity. Morphogen's own fields go under
`spec.morphogen`: an option is a Component marked `candidate`, a cell's rules sit on the entity it judges, and an
interface's tests sit on its API. The operator's private file (held-out answers, sandbox, budget) stays outside the
catalog. Backstage can show it all as a web UI and is never required. **How it ships:** a core Python package (CLI,
MCP server, schemas, judge), Agent Skills folders any harness can load, and a thin package per harness (the Claude
Code plugin first). The proposal is `docs/morphogen-kit.md`.

## The kernel, above the kit

The kernel stores and governs. Its `encoder-backstage` ingests Morphogen's catalog files as claims, so a map can be
searched, traversed and reviewed there. Its core ships without Substrate's parts. Its desktop (windows, a launcher,
framed apps) stays in the kernel and grows there (S-214).

## Substrate: the default distribution (S-211 to S-214)

**What it is:** an agent harness configured to get things done with the kernel and Morphogen, interactively. It
starts with Claude Code for the Anthropic subscription; OpenHands is a candidate if a harness built to run for
months is needed. It adds no core of its own.

**What it adds:**

| Part | Type |
| --- | --- |
| The live environment: signals, a queue per actuator, gates (`free`, `propose`, `deny`) whose `propose` goes to the kernel's review lane, the record | a kernel module (it needs the kernel's database and review lane) |
| The channel: an environment's events into a harness session | an MCP server |
| The MCP router: one endpoint for every tool, each call an action behind its gate | an MCP server, run as a compose service |
| The assistant's conversation | a view installed into the kernel's desktop |
| The harness's configuration: settings, hooks, MCP servers, Morphogen's plugin pinned | configuration |
| The model gateway (Bifrost) and local models (llama.cpp, Ollama) | compose services, configured |
| Bringing it up and checking it (`scripts/`, the compose file) | the distribution's own |

**The rule** (S-213): a part is a kernel module only when it needs the kernel. Otherwise it is the standard thing it
already is: an Agent Skill, an MCP server, a compose service or an outside service. `docs/parts.md` lists every
part of the tree and where it goes.

**The bet** (S-211): an ordinary strong harness in a well-built environment is the agent we want. It holds where
one implementation project runs end to end on a demo small business with no new core code, and it fails wherever
that run needs some.

## MetaSoar: System 1 skills

An Agent Skill's folder can hold scripts and other files, not just instructions. A System 1 skill adds three things
by convention: **policies** (a response script and its trigger), **observers** (how state is watched for triggers)
and **cases** (the record each policy was learned from and is judged on). The observer is a swappable interface:
state goes in, a policy and a confidence come out. It can be a feature-detector script, rules, a small model's
probabilities, the nearest past case or a tabular model. Below the confidence threshold, the model reads the skill's
instructions as it does today; the case is recorded and can become a new policy. Every policy and observer is a
Morphogen cell, judged by something other than its author. The spec is MetaSoar's (`docs/system1-skills.md`, M-19).

## The business (S-210)

Morphogen mapping small and medium businesses: their organisation and systems mapped, optimisation opportunities
found, each written up as an implementation project. It can run with a client's own material and access, or on
public sources as prospecting before a first call. Substrate is how those projects are then carried out for a
client. The business itself is worked in a session of its own.

## Contracts

| Between | Contract |
| --- | --- |
| a map, its catalogs and its targets | Backstage entity files, Morphogen's fields under `spec.morphogen` |
| a harness and its tools | MCP; Agent Skills; hooks |
| an optimiser and the judge | Morphogen's cells: a space, an evaluator the optimiser does not hold, one verdict |
| an environment and its agents | OpenEnv (episodes, rubrics, simulation), MCP |
| a caller and a model | an OpenAI- or Anthropic-compatible endpoint |
| a module and the kernel | the kernel's module contract (a manifest, its code, its own role) |

## Rules that still run through it

- **Gates:** `free`, `propose` (waits for a person), `deny`; enforced by the database, and by hooks inside the
  harness so a sub-agent cannot route around them.
- **Who proposes never grades their own work:** the judge (a cell's tests, an environment's rubric) is outside
  what is being changed.
- **Labels are outcomes,** never a decider's own choice; feedback may arrive long after, by the id of what it judges.
- **Privacy:** `docs/privacy.md`; nothing personal leaves the machine unless a rule is loosened for a named stream.
