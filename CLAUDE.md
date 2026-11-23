# Substrate

An operating system for AI agents (S-185): a top-level orchestrator (an ordinary LLM harness given skills, MCP
servers and hooks) that maps, orchestrates and optimises a working system, on a kernel made of Postgres where
everything is an object. Its shape is `docs/framework.md`; what is built next is `docs/plan.md` ("Next, in order"),
the one plan; every default and its reason is in `DECISIONS.md` (append-only). Read the plan first.

This is the **fresh tree** (S-137). v1 is tagged `v1-final` and its plans are in `docs/archive/`: history, not
plans to work from. v1's databases are kept in the same Postgres volume (`workbench`, `gateway`) and dumped in
`.state/backups/`; what people stated there comes back as data imported into the new store.

The layers (S-185, `docs/framework.md`, `docs/repos.md`): **the Kernel** (Postgres made into a kernel), **Substrate**
(the orchestrator kit, the adapters, the reference stack), **Morphogen** (the optimiser, a Claude Code plugin),
**distributions** (folders in `distributions/` here for now), **MetaSoar** (the research). Every dependency is a
contract, never another project's code. Environments are OpenEnv environments (S-184). Name parts by their role and
models by their alias (`fast`, `slow`, `cloud`), never by model. **The table below is what is in the tree today:**
the companion, voice head, worker, blocks and the ladder's experience store are the assistant distribution's parts
and move into `distributions/assistant/` (plan step 3).

| Part | Where | Role |
| --- | --- | --- |
| The store | the Knowledge Kernel (S-153, S-154, S-156: the UI and the skills read it from the kernel's database `kernel`, the agent's tools are the kernel's MCP `substrate` profile; `scripts/kernel.sh`); the old `store` package is retired and its schema was dropped on 2026-11-23 (S-191; a dump is in `.state/backups/`) | Wikibase's data model with OpenWiki's pinned evidence (S-135, S-138): entities, statements with ranks, references, spans, revisions, a page per entity; the agent's tools over MCP, and maps, roles, interfaces and catalogs (S-139; the `map` and `catalog` skills) |
| envkit | `envkit/` (declarations in `envkit/declarations/`; tests: `python3 -m pytest envkit`) | The fast in-process scheduler (lockstep or realtime) for live play, one module contract with `environment/` (S-161); moved from MetaSoar |
| The real-time environment | `environment/` (schema `env` in `environment/sql/`, migrated by `environment/db.py`, the channel in `environment/channel.py`) on pgmq in the same Postgres | signals logged whole and fanned out as topics, a queue per actuator behind its gate (`free`, `propose`, `deny`), the channel into Claude Code, archived only on `ack` (S-143) |
| The model gateway | container `gateway` (Bifrost), `scripts/gateway.py` | every model call goes through it with its caller's key and is recorded there, not by the caller (S-77) |
| Local models | container `ollama`; containers `llm` and `llm-fast` (llama.cpp, profile `llm`) | Ollama for the store's embeddings; two chat models (S-169): the slow capable one, Inkling 2 Mini on the CPU, at the gateway as `local/slow`; the fast one, LFM3 1.7B on the GPU, as `fast/fast` (the alias names the role, not the model; Gemma is retired) |
| Tools | `bin/`, container `substrate-tools` | the scripts' Python and gitleaks, run in a container as you (S-19) |
| The gate (being built) | experience: `env.experience` (`environment/sql/008_experience.sql`, `environment/experience.py`, key `EXPERIENCE_KEY`; S-183); the decider's trial `scripts/trials/decider/`; the proxy next (`docs/plan.md` step 3) | System 1, in a proxy in front of the gateway: at every model call it recalls a response distilled from the assistant's experience (episodes of scenario, response, outcome): a skill, or a rung (`fast`, `slow`, `cloud`); TabICL over embeddings with outcome-labelled episodes from Postgres, the fast model's probabilities as cold start; impasses typed, outcomes attached later by episode id (S-178 to S-182) |
| The companion (to retire) | `deploy/companion` (compose service `companion`), `environment/companion.py` (service `environment`), the UI's `#/companion` | Claude Code on Haiku through the gateway's pass-through route on the owner's login, fed by the channel (S-136, S-144); becomes the assistant's `cloud` rung behind `propose`, then retires as a separate agent (S-181) |
| The voice head | `voice/` (compose service `voice`, profile `voice`) on 127.0.0.1:8110 | the companion's voice and face: microphone in over a WebSocket, Silero and Parakeet to text, the fast model deciding each turn by the tool it calls (talk, quick tools such as notes, reminders, lookup and SearXNG search, or delegate), Kokoro to speak, a face that moves with it; delegated work goes to the worker on the slow model, not the companion (S-147, S-170, S-171) |
| The worker (becoming the assistant) | `environment/worker.py` (environment `worker`), `deploy/worker/` (compose service `worker`, profile `llm`, the kernel's image plus `openai`), the UI's `#/worker` | the assistant's one loop (S-181); today an agent on the self-hosted slow model (`local/slow` through the gateway as caller `worker:loop`; S-165, S-169): our own loop on `mcp` + `openai` (S-162); the kernel's `memory` profile over stdio and a few workspace tools; `gate(state)` before every model call is M-17's seam (S-163) |
| Blocks | `blocks/` (`block.yaml` blocks, JSON plans, `blocks/run.py` the default executor, `blocks/executor.yaml`; tests: `scripts/tests/test_blocks.py`) | what the agent compiles from what it solved: catalog entries with an interface and effects, assembled as P-Plan plans, run without the model; `skill_gate` plugs into the worker's `gate` (S-157, S-164) |
| Components and the judge | `env.component` and `env.verdict` (`environment/sql/007_components.sql`), `environment/author.py`, `environment/judge.py` (compose service `judge`), `judge/cases` (the judge's only) | every version of a component with its card; an author proposes from the record, the judge tests it against the active one on cases the author cannot read, the owner activates (S-151) |
| The UI | `ui/` (`ui/server.py`, `ui/static`), compose service `ui` on 127.0.0.1:8100 | the store's pages and maps as diagrams (S-140), read-only; v1's Workbench rebuilt, with no name of its own (S-141) |
| Images | `.github/workflows/images.yml`, `image_ref` in `scripts/lib.sh` | `ghcr.io/openreplicant/substrate-{db,tools,companion,worker}` and the kernel's image are pulled (tags `SUBSTRATE_IMAGE_TAG`, `KERNEL_IMAGE_TAG`); compose keeps `build:` as the fallback; voice is built locally, never published (S-167) |
| Glue | `scripts/`, `deploy/` | brings the parts up and connects them |

`deploy/caddy` (in front of the UI) and `deploy/ontop` (SPARQL) are kept and not started yet.

## Rules

1. **Look it up, then pin it.** Read a tool's current docs before relying on it (versions, flags, config keys);
   pin exact versions; prefer releases at least two weeks old; record what you pinned and where you read it, in
   `DECISIONS.md` when it is a default.
2. **Core first, open always.** Add a part, code or a view when a plan step's check needs it, and say which.
3. **Choose from catalogs, not memory**: the `research` skill, for any component, library, service or model.
4. **Secrets live in `.env`** (gitignored, mode 600), read through `env_value` and the `sec_*` verbs
   (`scripts/lib.sh`). Never print one into a committed file, a log, a commit message or chat. `.env.example`
   lists every setting, empty; `deploy/secrets.txt` says how each secret is made.
5. **One tested path.** Compose with Podman. Scripts call only the runtime's four verbs (`rt_up`, `rt_down`,
   `rt_status`, `rt_logs`) and keep engine-specific code in `scripts/lib.sh`.
6. **Nothing installed on the host** beyond git, python3 (standard library), the engine and its compose, and
   Claude Code. A tool goes into a container (`deploy/tools/Containerfile`, or the companion's).
7. **Licences:** permissive or LGPL for what the repository contains or links into Substrate's code. A GPL part may
   be a default when it is fetched at setup (never in the repository), runs unmodified in its own container and is
   reached over a process boundary (S-146). Models and tools the user downloads themselves (never bundled or
   committed) may be recommended whatever their licence, with the licence named (S-188). Check before adding.
8. **Every change ends with `scripts/check.sh` passing**, and `scripts/test.sh` where tests exist, or with the
   failure named and explained.
9. **Morphogen is the optimiser** (S-185; it was out of the build only so it could be iterated on quickly): use it
   through its contract (the cell file, its Claude Code plugin and MCP server), never by importing its code; change
   it only by pull request in its own repository, like any upstream project (the `upstream` skill).

## Working with the owner

- Recommend one option and keep moving; ask only for decisions that are theirs (positioning, licences, privacy,
  spending money, what to build next). Say what you recommend when you ask.
- Plain words; describe the loop plainly rather than reaching for broad framings.
- Decisions go in `DECISIONS.md` as new rows (append-only; supersede, never edit a committed row).
- Use the smallest model that can do a subtask (subagents on Haiku unless judgment is needed).

## Commands

```sh
scripts/bootstrap.sh       # once per machine: host tools, images (pulled from ghcr.io/openreplicant, built when not; S-167), the tools container
scripts/up.sh              # the stack (db, gateway, ollama, ui), the tools container, the databases; then check.sh
scripts/check.sh           # is everything up and wired
scripts/test.sh [FILE...]  # the test suites, in the tools container
scripts/build.sh [db|tools|companion|voice|kernel|worker]   # none: pull published images, build what did not pull; SUBSTRATE_BUILD=1 builds all
scripts/logs.sh SERVICE    # db, gateway, ollama, ui, environment, companion, llm, voice
scripts/tools.sh start|stop|status
scripts/kernel.sh init|export|login NAME|mcp NAME   # the Knowledge Kernel: schema, one-off export of the old `store` schema (now dropped), an agent's login and its MCP server
scripts/down.sh [--volumes]   # stop (deleting data asks first)
python3 scripts/gateway.py render|keys   # the gateway's config from .env and its callers
bin/in-tools python3 scripts/db.py init   # the databases and the environment's schema (environment/sql/)
bin/in-tools python3 scripts/env.py waiting|decide|publish|actuators|gate|queues   # the environment, as a person
scripts/companion.sh login|attach|restart|status   # the companion's session (log in once)
```
