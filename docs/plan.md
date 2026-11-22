# Plan

The one current plan (S-124, 2026-11-17). It replaces the plans in `docs/archive/` (the spec and its build plan,
the experiment-first direction, the handoff, the task briefs); those are kept as history and are not to be worked
from. Every default and its reason is still in `DECISIONS.md`.

## What Substrate is now

An agent framework. You put an environment on a system you need, run it, and watch and change it in the UI,
Substrate's web page over the store (`ui/`, S-140, S-141; rebuilt on the fresh tree, S-137). Its shape is `docs/framework.md` (S-125): the environment is data in
Postgres, pass-through to Claude Code is the default, components distilled from the record carry cards, a judge
tests them on cases their author never saw, and environments nest. Morphogen stays a part you can use as it is;
no more work goes into it for now.

## The fresh start (S-137)

v1 is tagged `v1-final` and archived. The fresh tree keeps only: the Postgres image (pgvector, pgmq, pg_cron,
pgGraph), the model gateway (Bifrost, per-caller keys, the meter), Caddy, compose and `scripts/lib.sh`, the tools
container, `docs/privacy.md`, this plan, `docs/framework.md`, `DECISIONS.md`, `lookups`' recorded cases as data,
and the `setup`, `research` and `upstream` skills. Everything else is rebuilt on the new store (S-135) or left
in v1. v1's databases are in `.state/backups/` (2026-11-17); what people stated there comes back as data.

## Steps

| # | Step | Done when |
| --- | --- | --- |
| 1 | Get the stack up on the machine you work on (`setup` skill) | done 2026-11-17 on v1; redone on the fresh tree: `scripts/check.sh` passes |
| 2 | Read the closest works and amend `docs/framework.md` | done (S-129; Wikibase and OpenWiki, S-135) |
| 3 | The owner picks the first system | done (S-130): the companion, a persistent voice and avatar assistant that works in the background and manages its own model and compute budget, the first child of the chimera (the root environment) |
| 3a | **The fresh tree** (S-137): delete what is not carried over in one commit; `setup` and `check.sh` pass on what remains | done 2026-11-17: db (database `substrate` beside v1's), gateway, ollama and the tools container up from the fresh tree; `scripts/check.sh` and `scripts/test.sh` pass |
| 3b | **The store** (S-135): entity, statement, reference, span, revision; typed values; ranks and the usable value; constraints on properties, reported; a page per entity; hash-pinned spans that flag what cites them; the agent's `search`, `read`, `expand`, `locate` over MCP; Ontop in Wikidata's two RDF shapes, pgGraph, pgvector; v1's people's statements, open decisions and interview answers imported | tests in a throwaway database pass; a changed span flags its statements and what was derived from them, with no model call; v1's imported statements are readable as pages — core done 2026-11-17 (S-138): the model, ranks, constraints, pages, pinned spans and flags, the four tools over MCP, v1's import, the graph over pgGraph; all three checks pass. Then maps, roles, interfaces and catalogs (S-139): the vocabulary, MCP writes, the `map` and `catalog` skills. Substrate mapped into the store with the `map` skill, and maps seen as diagrams in the UI's first page (S-140: `store.map`, Cytoscape.js with dagre, the `ui` service). Parked (S-142): the embedding model and vectors on spans and pages, until the companion's record gives real queries; Ontop when something uses SPARQL |
| 3c | **The real-time environment:** pgmq topics for streams (`<env>.<stream>.<kind>`), a queue per actuator, gates (`free`, `propose`, `deny`), proposals as decisions, escalation as a topic; the channel server (stdio MCP, `claude/channel`, archived only on `ack`) | a published signal reaches a subscribed channel, an unacknowledged one comes back, an actuator call behind `propose` waits for a person — done 2026-11-17 (S-143): schema `env` and `environment/`, the channel speaking the documented `claude/channel` contract, `scripts/env.py` for a person's decisions; `scripts/tests/test_environment.py` passes (32 checks). Not yet seen: a live Claude Code session receiving it, which is step 4's first test |
| 3d | **The store moves to the Knowledge Kernel** (S-153; `docs/store-to-kernel.md`), shortest path first: a `substrate` vocabulary pack (properties, maps, roles, interfaces, catalogs); a one-off exporter from `store` into kernel change sets; a read-model module (usable values, a page per entity, maps, search); a `substrate` profile in kernel-mcp with the store's tools (`search`, `read`, `expand`, `locate`, `path`, `alternatives`, `violations`, `create_item`, `say`, `deprecate`); then the UI, the skills and the tests repointed; the span-change watcher and reported constraints as processors; the graph once `current_edge` exists (D-86); last, the `env` schema and its migrator moved out of `store/` (four environment processes import from `store.mcp`) and `store/` retired | the UI, the `map` and `catalog` skills and `scripts/test.sh` pass on the kernel; v1's imported statements read the same as pages; a changed span still flags what cites it with no model call; nothing in the tree imports `store` — in progress 2026-11-21 (S-154): the UI, the `map`, `catalog`, `research` and `setup` skills, the deploy files and the store and UI tests repointed to the kernel (skills use `mcp__kernel__*`); deployed on Podman (S-155); the `env` schema and its migrator moved to `environment/` and `store/` retired, so nothing in the tree imports `store` (S-156, 2026-11-21: that item and the step's last check are done); left: the span-change watcher and reported constraints, the graph, v1's pages compared |
| 4 | **The companion, text first, pass-through.** In its own container (S-136), on Haiku with the owner's login through the gateway. Its streams: the owner's messages, the gateway's meter (spend per caller), a clock. Its actuators: reply, start a background task, propose a budget or model change. A Claude Code session kept open, fed by the channel. The privacy defaults (`docs/privacy.md`) apply, P3 and P4 loosened for its text stream only (S-136). A small page to talk to it. First test inside it: does a channel work with Claude Code through the gateway (subscription mode) | the owner talks to it in text and it does background work end to end; every signal, call and action is in the record; budget changes are proposals the owner decides  — built 2026-11-17 (S-144): the container, the environment `companion` (streams, actuators, the budget's gate), the `companion` login, the page at the UI's `#/companion`, the gateway's `/anthropic_passthrough` route; `scripts/tests/test_companion.py` passes. Done 2026-11-18 (S-145): on the owner's login through the gateway, a message and its reply, a background task end to end, and a budget proposal the owner approved, every call in the gateway's log |
| 5 | **The browser client as an environment, and the voice head.** A two-way media path on the UI's server; the browser's microphone and speaker as sensor and actuator. The voice head as a pipeline component: voice activity, speech-to-text (Parakeet TDT), a fast local model for turn-taking and short answers, text-to-speech (Kokoro, Rust); versions and placement (GPU or CPU on the 1070) checked with the `research` skill and measured. It answers what it can and hands real work to the Claude Code session, which reports back through it | a spoken conversation with latency the owner accepts; LLM calls per event and cost per hour on its card — first loop up 2026-11-18 (S-147, S-149): Parakeet 110M and Kokoro on the CPU, Gemma 4 26B-A4B on llama.cpp (`llm`), the voice head with a canvas face at 127.0.0.1:8110 (`voice`), handing real work to the companion; waiting on the owner's own voice |
| 6 | One distilled component with its card, and the judge interface's first filler (a script as the judge user, a held-out slice of the record, whole days held out) | a verdict on the component against pass-through; promoted or refused on it  — first loop 2026-11-18 (S-151), early, on the voice head: components with cards in `env.component`, an author on the local model, the judge (`judge`, its own login, labelled cases only it mounts, a held-out third of the record), verdicts kept whole, activation by the owner. A component compared against its incumbent, not yet against pass-through; held out by hash, not yet by whole days |
| 7 | Sight: the camera as a sensor, a fast path (motion, presence, landmarks) and a slow path (a vision model on demand) as components | the companion notices and answers about what it sees, with refresh rate and cost per hour on the cards |
| 8 | **The avatar, then mixed reality on the Quest 3.** The talking head first (three.js, `@pixiv/three-vrm`, mouth by expression presets); then the browser environment in an `immersive-ar` WebXR session: planes, meshes, anchors, depth, head and hand pose as sensors; the avatar placed in the room (`move_to`, `place_on`, `look_at`). First test on the device: does `getUserMedia` give the passthrough camera (if not, a native Quest app as another adapter) | the avatar talks, stays where it was put in the room and looks at the owner; recognition components on their cards (where they run, how often, cost) |
| 9 | **Adaptive video game playing** (S-142): after the avatar, the companion plays games as environments (the screen and game state as sensors, input as gated actuators) and gets better at a game from its own record, by distilled components judged against pass-through | the owner picks the first game; done-when is set then |
| 10 | The next embodied child: Resonite (in-world editing; ResoniteLink's WebSocket and community MCP servers, every world-changing tool gated), VRChat, Virt-A-Mate or a ROS2 simulation (the owner's pick), by the same adapter pattern | the companion acts there through the same avatar actuators, under the same gates and budget |

Self-levers beyond budget and model choice, and the other layers in `docs/framework.md`, come as these steps
need them, each tested against pass-through. The UI is no longer frozen: add what these steps need, and
nothing they don't.

## The runtime, components and agents (S-173, 2026-11-22)

The owner's direction, after comparing harnesses (S-172) and RuleGo: our own light runtime on what is already here,
not a framework or a harness per slot.

- **Postgres is the backbone:** pgmq for queues, the `env` schema for gates and the record, the kernel for the
  catalog of components and MCP servers. No other broker or registry.
- **MCP is every component's interface, both ways** (RuleGo's good idea): a block is an MCP tool (one blocks MCP
  server exposes each block by its declared interface, world-changing ones behind their `blocks.<name>` gate), and a
  registered MCP server's tools are components in the catalog, gated and composable like blocks. An aggregating MCP
  endpoint gives each agent the tools it may use (Bifrost's MCP side is the first candidate to check).
- **Light by default:** a block runs on demand, a short-lived process per call (measured: about 19 ms for a Python
  block with JSON in and out, 8 MB idle), with a `hot` toggle that keeps it running as a supervised process when a
  measured plan needs it. Go where the hot paths already are (the gateway, the supervisor); ours moves to Go only
  when a measurement says so.
- **Processes, not only containers:** a process supervisor in one small container runs the hot blocks and agent
  processes; Compose keeps the services. Nomad is out by default (Business Source License); process-compose
  (Apache-2.0, Go) is the lead candidate, to be picked with the `research` skill against s6, supervisord and
  systemd units.
- **One agent loop of ours** (the worker's, generalised): models through the gateway, M-17's skill gate at the model
  endpoint, tools from the MCP registry, world-changing calls through the environment's gates. The voice front-end
  stays its fast specialisation (S-170, S-171).
- **Observability is part of the runtime** (the owner, 2026-11-22): OpenTelemetry through every layer, one trace per
  task from its queue message through the loop's steps, each model call at the gateway, each MCP tool or block call
  and each gate decision (the GenAI semantic conventions for model spans). An OTel Collector, picked with the
  `research` skill, takes OTLP from our processes, the gateway and the supervisor; traces go to a viewer, metrics to
  Prometheus, which the kernel's `observer-prometheus` already turns into observed claims (S-05, the kernel's D-119),
  so a component's card carries measured latency and cost. Postgres stays the system of record (decisions, outcomes,
  claims); telemetry sits beside it.
- **The kernel's boundary:** the bus (pgmq transport, the `env` tables) stays in Substrate's schema in the same
  Postgres, because the kernel's modules never write tables and real-time signals are too many to be claims; what is
  worth knowing crosses as claims through an encoder (`encoder-substrate`), the component and MCP registry lives in
  the kernel as claims, and `propose`-gated actions are meant to reach the kernel's review lane so a person approves in
  one place (option A, recommended; a sanctioned runtime layer inside the kernel, option B, only if something outside
  Substrate needs the bus; the owner to confirm).
- **Other harnesses are agent instances, not conformed to:** an instance reads tasks from its queue, takes tools from
  the MCP endpoint, calls models through the gateway and publishes `task.done`. Claude Code (the owner's
  subscription) is the first, as the companion already is; OpenCode, Codex and others get one adapter each when
  wanted (`scripts/trials/harness/candidates.json` holds the surveyed list).

## Next, in order (2026-11-22)

1. **The process supervisor and the telemetry collector**, picked with the `research` skill (the supervisor:
   on-demand and hot processes, restarts, health, an API to start and stop, its footprint; the collector: OTLP in,
   traces to a viewer, metrics to Prometheus, permissive, light).
2. **The MCP registry and the blocks MCP server:** blocks as MCP tools on demand, gates enforced; registered MCP
   servers listed as components. Done when the worker calls a block and a registered server's tool through it.
3. **The worker on the registry:** its own file tools and the voice head's quick tools (`voice/tools.py`) replaced
   by MCP servers; one loop for the worker, the fast layer reusing it.
4. **M-17's gate at the model endpoint**, then M-17's first experiment (the handoff, 2026-11-22).
5. **The agent-instance contract**, Claude Code first.
6. Then, as before: the live map and avatar page (S-158), the business distribution, process KPIs and one real
   actuator beyond Compose behind a gate.

Done from the 2026-11-21 list: offline agents on the local model (S-162, S-163, now Inkling, S-169), blocks and the
default executor (S-164).

## Deferred

Morphogen R&D (statistics, the judge's own gateway and meter, the queue, GitHub Actions, the evidence log), the
case-and-scorer kit and the environment contract's generalisation, held-out cases by script, the paper catalog's
publication and reproductions, the hosted mapper and hosted judging, the slot model
(`docs/archive/slots.md`).

## The owner's to decide

- Which game comes first (step 9), and which embodied environment after that (step 10).
- Rotating the Postgres password; putting the Gemma model at the gateway.
- The licence and whether the repository goes public.
- Whether a Business-Source-licensed part (Nomad) may ever be a default; recommended no (S-173).
- Whether LFM3 (LFM Open License v1.0) may be the recommended fast model (S-169).
