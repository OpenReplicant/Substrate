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

> **Preview release (v0.1.0-preview.1, 2026-11-27).** The stack below installs from a fresh clone and passes its
> checks and tests, but Substrate is in the middle of a re-cut (`docs/plan.md`, "The re-cut"; `docs/parts.md`,
> "Order"): its parts are moving into their final types, and names, services and settings will change before 0.1.0.
> Use it to try the stack and the desktop, not as something to build on yet.

**Where it stands (2026-11-27):** the re-cut's kit is done: Morphogen maps a made-up firm from its material to a
report of implementation projects with no kernel and no stack (Morphogen #102 to #104; S-216, S-217). Substrate uses
Morphogen's plugin like any user (pinned to `d945a9c`, plugin 0.9.0). The stack runs on the kernel at `e4ed8e2`,
and a person has talked to the assistant in the kernel's desktop (S-208, S-218). The re-cut's step 2 is done (S-219 to S-221): the environment is a kernel
module whose proposals a person decides in the kernel's review lane, the channel and the router are MCP servers on
it, and the assistant's view is already a view in the kernel's desktop. Next is the default distribution.

## Preview: what works, what is moving

**Works in this preview** (checked on a fresh clone, 2026-11-27: `scripts/bootstrap.sh`, `scripts/up.sh`,
`scripts/check.sh` all passing, and `scripts/test.sh`: catalog 9, environment 41, gateway 15, kernel 27, UI 36,
release 10 checks, the router's Go tests):

- the stack from published images, pinned to this release (Substrate `0.1.0-preview.1`, the kernel `0.1.0`), or built
  here when they do not pull;
- the desktop (the kernel's shell) at http://127.0.0.1:8080/ with search, review, change sets, the graph, the view
  modules, and the framed apps: the gateway's dashboard, Substrate's map pages and the MCP router's page;
- a person's sign-in (`scripts/kernel.sh person NAME`) and an agent's own login with the kernel's MCP tools
  (`scripts/kernel.sh login NAME`);
- the environment as a kernel module: a proposed action (a gated tool call among them) waits in the kernel's review
  lane, and a person decides it in the desktop's Review with everything else the kernel holds for review (S-219);
- the MCP router: one endpoint in front of the kernel's and the desktop's tools, read-only tools free, every tool that
  writes waiting for a person's decision;
- the assistant (`scripts/assistant.sh`): a Claude Code session you talk to in the desktop's Assistant window;
- the model gateway (Bifrost) with a key per caller and every call logged without content, and Ollama behind it;
- Morphogen's plugin (map, research, catalog, optimise) in Claude Code, on Substrate's own catalog.

**Moving** (expect changes before 0.1.0):

- the assistant's view gets what it lacks (a chat library) when its next use case asks (S-221);
- `ui/` (the old store pages, on :8100) is kept for now; it goes once the kernel's views and a map viewer do its job;
- the kernel's Substrate-specific modules (`encoder-substrate`, `view-substrate`, kernel-mcp's `substrate` profile)
  are retired once Morphogen's file-based skills replace them; `scripts/kernel.sh mcp` uses that profile today;
- the compose file becomes the default distribution: the kernel's core and Substrate's modules installed onto it.

**Known limits of the preview:** tested on one Linux machine with rootless Podman only (Docker should work through
`CONTAINER_ENGINE=docker` but was not tried for this release); everything binds to 127.0.0.1, with no HTTPS and no
multi-user setup; the local models (`llm`, `llm-fast`) need an NVIDIA GPU's driver libraries and your own GGUF files;
`scripts/kernel.sh mcp` and the assistant need Claude Code; there is no upgrade path promised from this preview to
the next release (keep your data volume, but expect to re-run `scripts/up.sh` and possibly re-initialise).

## What runs

The stack as it is in the tree today, while the parts move (`docs/parts.md`). Everything is in containers under
Podman compose, published on 127.0.0.1 only.

| Part | Where | What it does |
| --- | --- | --- |
| The kernel | the Knowledge Kernel's image (`ghcr.io/openreplicant/kernel`), its database `kernel` in the stack's Postgres (`deploy/postgres`), `scripts/kernel.sh` | Knowledge with provenance: every claim attributed, cited and reviewed; logins and row-level security; the record. Substrate's catalog (`catalog/`) is read into it as Backstage entities |
| The desktop | service `caddy` (`deploy/caddy/`) in front of the kernel's `kk serve`, http://127.0.0.1:8080/ | The kernel's UI shell as a desktop: a launcher and windows, framed apps each on an origin of its own (:8081 to :8083), MCP over HTTP at `/mcp` |
| The environment | `environment/`, schema `env`, a kernel module (service `environment`) | Signals logged whole and fanned out as pgmq topics; one queue per actuator behind a gate (`free`, `propose`, `deny`); a proposal waits in the kernel's review lane and a person decides it in the desktop's Review, with everything else the kernel holds for review; every action recorded (S-219) |
| The channel | `environment/channel.py`, an MCP server | Pushes an environment's signals into a live Claude Code session, as a login of its own; a signal not acknowledged comes back (S-220) |
| The MCP router | `mcp-router/` (Go), services `mcp-router`, `mcp-kernel`, `mcp-desktop`; http://127.0.0.1:8083/ | One MCP endpoint for agents in front of every connected MCP server; each tool an actuator behind its gate, each call recorded, writers waiting for a person's decision in the desktop's Review |
| The assistant | `desktop/`, services `desktop`, `mcp-desktop`; `scripts/assistant.sh` | The conversation between a person and the agents as signals: you talk in the desktop's Assistant window, a Claude Code session hears it on the channel and answers through the router |
| The gateway | `gateway` (Bifrost), `scripts/gateway.py` | Every model call goes through it under its caller's key and is logged there, not by the caller. Keys decide which providers a caller may reach; a meter counts a judged run's calls (S-193) |
| The local models | `ollama`; services `llm` and `llm-fast` (llama.cpp, profile `llm`) | Ollama for embeddings; two of your own GGUFs (S-169): a slow capable one on the CPU (`slow`) and a small fast one on the GPU (`fast`) |
| The optimiser | Morphogen's Claude Code plugin; its rules in the catalog (`catalog-info.yaml` at the root, S-216) | Cells from Substrate's catalog (`catalog/`); a change is judged on cases it cannot read, its model calls counted at the gateway (S-193) |
| The old store UI | `ui/`, service `ui`, http://127.0.0.1:8100 | The kernel's read model as pages and maps, read-only; to be retired (above) |
| The tools container | `deploy/tools/`, `bin/` | The scripts' Python and gitleaks, run in a container as you, so the host needs almost nothing |

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

## Requirements

- **Linux on x86_64.** Tested on Ubuntu 24.04 (kernel 6.8). macOS and Windows are untested.
- **Podman with a compose provider** (tested: rootless Podman 4.9.3 with Docker Compose v5.8.0 as its provider;
  `podman compose version` must answer), or Docker with compose v2 (`CONTAINER_ENGINE=docker` in `.env`; untested).
- **git, python3** (3.9 or later, standard library only) **and curl** on the host. Nothing else is installed there.
- **Disk:** about 7 GB for the images (Ollama's is 5 GB of it), plus whatever models you pull or point at.
- **Memory:** the core stack uses about 0.5 GB at rest; local models need what their GGUF files need on top.
- **Network:** the first run pulls images from ghcr.io and docker.io (public; no login needed).
- **Optional:** Claude Code (the assistant, `scripts/kernel.sh mcp`, Morphogen's plugin) and uv (the plugin runs its
  MCP server with it); an NVIDIA GPU and your own GGUF files for the local models; an OpenRouter key for its free models.
- **Ports on 127.0.0.1:** 5432 (Postgres), 8080 (the desktop), 8081 to 8083 (its framed apps), 8090 (the gateway),
  8100 (the old UI), 11434 (Ollama). Each is a setting in `.env` (below).

## Running it

```sh
git clone https://github.com/OpenReplicant/Substrate && cd Substrate
scripts/bootstrap.sh       # once: checks the host tools, makes .env and its secrets, pulls the images, starts the tools container
scripts/up.sh              # the stack and its databases, then scripts/check.sh
scripts/check.sh           # is everything up and wired
scripts/test.sh            # the test suites, each in a throwaway database
scripts/kernel.sh person NAME   # your sign-in for the desktop (the password is kept in .state/kernel/, never printed)
```

Then open http://127.0.0.1:8080/ and sign in as NAME. `scripts/down.sh` stops the stack (`--volumes` deletes its
data, and asks first).

Settings live in `.env` (made from `.env.example` by `scripts/bootstrap.sh`, mode 600; secrets are generated once and
never printed). The images are this release's by default (`SUBSTRATE_IMAGE_TAG`, `KERNEL_IMAGE_TAG`; `main` follows
the main branches); one that does not pull is built here. The first `scripts/up.sh` takes a few minutes.

**When a port is taken, or for a second copy on one machine:** run `scripts/settings.sh` first (it makes `.env`),
change the settings below in `.env`, then run `scripts/bootstrap.sh` and `scripts/up.sh` as above. A port: `DB_PORT`,
`DESKTOP_PORT`, `DESKTOP_GATEWAY_PORT`, `DESKTOP_MAPS_PORT`, `DESKTOP_ROUTER_PORT`, `GATEWAY_PORT`, `UI_PORT`,
`OLLAMA_PORT`. A second copy also needs its own `COMPOSE_PROJECT_NAME`, `TOOLS_CONTAINER`, `DB_VOLUME`,
`OLLAMA_VOLUME` and `KERNEL_ARTIFACTS_VOLUME`; with the defaults it would share the first copy's data.
`scripts/tools.sh` refuses to replace another checkout's tools container.

**Local models (optional):** set `LLM_MODELS_DIR` and `LLM_MODEL` (and `LLM_FAST_MODELS_DIR`, `LLM_FAST_MODEL`) to your
GGUF files and `COMPOSE_PROFILES=llm`; on a GPU, `NVIDIA_LIB_DIR` if the driver's libraries are not in
`/usr/lib/x86_64-linux-gnu`.

## Privacy

The defaults are in [`docs/privacy.md`](docs/privacy.md): nothing personal leaves the machine unless a rule is
loosened for a named stream, and each loosening is a recorded decision. The gateway keeps no message content; the
local models keep everything on this machine.

## Not built yet

`docs/plan.md`, "The re-cut", and `docs/parts.md`, "Order": Substrate's parts in their types (under way), the
default distribution, and the test of the bet: one implementation project on a demo small business, carried out
under the kernel's gates. What this release is and what comes next: `docs/release-notes/v0.1.0-preview.1.md`.

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
