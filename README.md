# Substrate

> **Map, design and orchestrate software, agents and organisations. Optimise all the things!**

**The default distribution:** an agent harness set up to get things done with two products, interactively. It
starts with Claude Code, for its Anthropic subscription. Substrate adds no core of its own. It is the configuration,
the optional parts installed onto the kernel, and the stack that runs them (S-211 to S-214).

| Project | What it is |
| --- | --- |
| **[Morphogen](https://github.com/OpenReplicant/Morphogen)** | **the kit:** map a system (interviews, design work, fact-finding), research and catalogue the options for each part, and optimise behind a judge the optimiser cannot edit. Files only, in Backstage's catalog format, on any harness; no database (S-209) |
| **[Knowledge Kernel](https://github.com/OpenReplicant/kernel)** | Postgres made into a kernel: knowledge with provenance, review, logins and row-level security, the record, a module contract, and a desktop in the browser. An optional layer above Morphogen: it ingests the same catalog files when indexing, search or graph traversal are wanted |
| **Substrate** (this repository) | the default distribution: the kernel's core, Substrate's optional parts installed onto it (the live environment and its gates, the channel into a harness, the MCP router, the assistant's view in the kernel's desktop), Morphogen's plugin, a configured harness, a model gateway and local models |
| **[MetaSoar](https://github.com/OpenReplicant/MetaSoar)** | the research: cognitive architecture, and System 1 skills (learned policies, observers and cases in an Agent Skill's folder, each judged as a Morphogen cell) |

A part of Substrate is a kernel module only when it needs the kernel: its own role, its data in the kernel's
database, the review lane. Otherwise it is the standard thing it already is: an Agent Skill, an MCP server, a
compose service or an outside service (S-213). Our agents and experiments are built on this distribution. Every
dependency is a contract (Backstage files, MCP, OpenEnv, Morphogen's cells, an OpenAI- or Anthropic-compatible
endpoint), never another project's code. The shape is [`docs/framework.md`](docs/framework.md); where each part
goes is [`docs/parts.md`](docs/parts.md); what is built next is [`docs/plan.md`](docs/plan.md).

**The bet:** an ordinary strong harness in a well-built environment is the agent we want. It holds where one
implementation project runs end to end on a demo small business without new core code: Morphogen maps the business
and picks an opportunity, the harness carries it out under the kernel's gates, a person approves what matters, and
Morphogen judges the result (S-211).

**Where it stands (2026-11-24):** the stack below runs on one machine, and a person has talked to the assistant in
the kernel's desktop (S-208). The re-cut is decided and the parts are not moved yet. The work goes to Morphogen
(the kit) and the kernel first.

## What runs

The stack as it is in the tree today, before the parts move (`docs/parts.md`). Everything is in containers under
Podman compose, published on 127.0.0.1 only.

| Part | Where | What it does |
| --- | --- | --- |
| The store | the Knowledge Kernel (`scripts/kernel.sh`), Postgres (`deploy/postgres`) | Wikibase's data model with pinned evidence: things, statements, and the exact span of the source each statement rests on. A changed source flags what cites it, with no model call. Maps of parts, roles and interfaces, and catalogs of candidates with measurements and trade-off notes |
| The environment | `environment/`, schema `env` | Signals logged whole and fanned out as pgmq topics; one queue per actuator behind a gate (`free`, `propose`, `deny`); proposals wait for a person; every action recorded |
| The channel | `environment/channel.py` | Pushes an environment's signals into a live Claude Code session; a signal not acknowledged comes back |
| The gateway | `gateway` (Bifrost), `scripts/gateway.py` | Every model call goes through it under its caller's key and is logged there, not by the caller. Keys decide which providers a caller may reach; a meter counts a judged run's calls (S-193) |
| The local models | services `llm` and `llm-fast` (llama.cpp) | Two of your own GGUFs (S-169): a slow capable one on the CPU (`slow`; Inkling 2 Mini here) and a small fast one on the GPU (`fast`; LFM3 1.7B here) |
| The optimiser | Morphogen's Claude Code plugin, `morphogen.yaml` | Cells from Substrate's catalog (`catalog/`); a change is judged on cases it cannot read, its model calls counted at the gateway (S-193) |
| The UI | `ui/`, service `ui`, http://127.0.0.1:8100 | The store's pages and maps as diagrams, read-only |

Who may do what is enforced by Postgres logins, not by convention: a process that runs a model can publish and
act, but cannot decide a proposal or change a gate. Every signal and action keeps the login that really wrote it,
whatever it claims to be.

## Experiments, and what they showed

Each choice was measured before it was made. The scripts are in `scripts/trials/`, the reasons in
`DECISIONS.md`.

**OpenEnv** (S-192; `scripts/trials/openenv`). openenv 0.12.0 with one Postgres-backed environment: many
sessions share one live environment because its state is in Postgres; events reach a subscriber from Postgres in
about 3 ms (OpenEnv itself pushes nothing); `reset` clones a template database in 60 to 80 ms; Claude Code runs as
an OpenEnv harness through a small adapter, against a model proxy, with the episode's id in a header; a skill's
answer (a tool call, then text) is accepted with no model; a rubric's score attaches to every model call of its
episode. MCP's `input_required` is in the 2026-07-28 revision, but OpenEnv's MCP library cannot use it yet, so
gates stay a `propose` tool.

**Morphogen** (S-193). A first cell, the old voice router's prompt, was judged end to end: its runs in Podman,
the gateway joined to each run's network, 40 model calls a run counted from the gateway's own log; a candidate
that gained 2.3% was refused as not significant (p = 0.0625 over 12 paired runs).

**A channel into Claude Code works through the gateway on a Claude login** (S-144, S-145). Bifrost's documented
subscription mode did not forward the login on any version tried (v2.3.2 to v2.5.1); its `/anthropic_passthrough`
route does, with the caller's key still required and its allowed models enforced.

**Earlier** (S-140, S-142). A diagram library for maps: Cytoscape.js with dagre drew Substrate's own map in
53 ms under the UI's strict content policy. Embeddings for search: on 213 pages no embedding model beat plain
full-text search beyond chance, so none is used until the record gives real queries. The first assistant's trials
(speech, the local models, the voice router, the decider) are in `DECISIONS.md` (S-147 to S-183) and git history.

## Running it

Needs git, python3, Podman with compose, Claude Code and uv (for Morphogen's plugin) on the host; everything else
runs in containers.

```sh
scripts/bootstrap.sh       # once: images and the tools container
scripts/up.sh              # the stack and its databases, then scripts/check.sh
scripts/check.sh           # is everything up and wired
scripts/test.sh            # the test suites, each in a throwaway database
```

Settings live in `.env` (made from `.env.example`, mode 600; secrets are generated once). For the local models,
set `LLM_MODELS_DIR` and `LLM_MODEL` (and `LLM_FAST_MODELS_DIR`, `LLM_FAST_MODEL`) to your GGUF files and
`COMPOSE_PROFILES=llm`.

## Privacy

The defaults are in [`docs/privacy.md`](docs/privacy.md): nothing personal leaves the machine unless a rule is
loosened for a named stream, and each loosening is a recorded decision. The gateway keeps no message content; the
local models keep everything on this machine.

## Not built yet

`docs/plan.md`, "The re-cut": Morphogen as the kit (its pull request), Substrate's parts in their types, the
default distribution, and the test of the bet on a demo small business.

## Where to read more

- [`docs/plan.md`](docs/plan.md): the steps, and where each stands
- [`docs/framework.md`](docs/framework.md): the shape: the projects, the contracts between them, what Substrate adds
- [`docs/parts.md`](docs/parts.md): every part of this tree and where it goes
- [`docs/morphogen-kit.md`](docs/morphogen-kit.md): Morphogen as the kit, the proposal for its pull request
- [`docs/repos.md`](docs/repos.md): what each repository owns and depends on
- [`docs/research/`](docs/research/): the prior-art research behind the shape (2026-11-23)
- [`docs/archive/framework-s185.md`](docs/archive/framework-s185.md): the shape before the re-cut (objects, traits, the orchestrator, OpenEnv), history
- [`DECISIONS.md`](DECISIONS.md): every default, every measurement behind it, and why (append-only)
- `CLAUDE.md`: the parts and the rules for working on it

This is the fresh tree (S-137); v1 is tagged `v1-final`, and its plans are in `docs/archive/`.

## Licence

Substrate is under the Apache License 2.0 (`LICENSE`). The models you point `LLM_MODEL` and `LLM_FAST_MODEL` at
carry their own licences.
