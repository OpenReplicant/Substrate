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

## Describe, check, decode: components and runtimes (S-174, 2026-11-22)

Supersedes S-173's runtime engine. The owner's direction: Substrate does not build a runtime or sit in the links
between components. It **describes** a system in the Knowledge Kernel, **checks** that its parts can talk, puts a
**translator** between two that cannot, and **decodes** the description into the native formats of existing runtimes
and **encodes** what they report back; "otherwise we would be just encoding and decoding, like file formats, for
existing runtimes". That is the kernel's own architecture: decoders turn models into running things, encoders read
them back, automations stay in their runners' native formats (the kernel's D-41; chain runners parked, D-36).

**The kernel as a symbolic latent space** (the owner): one universal symbolic representation that systems are
interpreted into (encoders) and out of (decoders). A map, a BPMN process, a compose file and a running deployment
are views of the same items and claims; what can be said in one format can be carried to another through it.

- **Components describe their interfaces; Substrate does not mediate them.** An interface is described in the shape
  of a W3C WoT Thing Description: the affordance (an action, property or event) with its data schema, and the forms
  that reach it (protocol, address, content type): MCP over stdio or HTTP, an OpenAI-compatible API, a pgmq queue
  (AsyncAPI describes one), plain HTTP, anything else. Components talk to each other directly, as they already do.
- **Compatibility is checked, and translators are components.** Two parts fit when one provides the interface the
  other requires (the map vocabulary's *provides interface* and *requires interface*). Where none fits directly, a
  translator from the catalog goes between them (an MCP bridge, a proxy, an adapter block), found like any other
  part.
- **The catalog entry is D-101's first content type.** Each component (block, MCP server, service, model, agent
  instance) is an item in the kernel: a typed document of fields and prose, with claims derived from it for checking,
  drift and alternatives (the kernel's D-101, proposed 2026-11-08, waits on exactly this proof).
- **Runtimes are pluggable, Compose first.** A decoder writes the map out in one runtime's format; an encoder reads
  its state back. Compose (with Podman) is the first, since Substrate runs on it; process-compose is the lead
  candidate for plain processes. `docs/compatibility/` lists the runtimes, orchestrators, cloud services and
  standards a decoder could target, with formats, APIs and licences: what to tell a business that already runs
  Kubernetes, Camunda or Step Functions. A licence decides only whether a part can be a default (rule 7).
- **Light by default.** Our blocks are components that implement some protocol, as clients or servers; they run on
  demand (measured: about 19 ms a call for a Python block with JSON in and out, 8 MB idle, S-173) or kept hot by the
  runtime when a measured plan needs it.
- **What stays ours, kept small:** the description and the compatibility check; the decoders and encoders; gates at
  the chokepoints that exist (the model gateway, an MCP proxy where one is chosen, our own agents' actuators), not on
  every link; the voice front-end's loop (S-170, S-171); M-17's gate at the model endpoint (a proxy or a Bifrost
  plugin).
- **The kernel's boundary is the kernel's own decisions:** queues belong to a distribution in its own database
  (D-94 c, decided), so the `env` schema stays Substrate's; signals and telemetry are observations, not claims ("a
  measurement is not content anyone wrote", D-101); what is worth knowing crosses as claims and items through an
  encoder (`encoder-substrate`); `propose`-gated actions are meant to reach the kernel's review lane, so a person
  approves in one place.
- **Observability:** OpenTelemetry where the parts already speak it (the gateway, the runtimes, our processes), an
  OTel Collector picked with the `research` skill, traces to a viewer and metrics to Prometheus, which the kernel's
  `observer-prometheus` turns into observed claims; a component's card carries measured latency and cost.
- **Agents:** our agent loop (the worker's) and the voice front-end are components; Claude Code (the owner's
  subscription) and other harnesses are agent instances, each a component with its own interfaces
  (`scripts/trials/harness/candidates.json` holds the surveyed list).

## Next, in order (2026-11-22)

1. **The catalog entry content type** (D-101's first): a component's item with its interfaces described WoT-style,
   and a compatibility check between two entries. Done when Substrate's own parts are entries and the check says
   which talk to which.
2. **The first decoder and encoder: the map to and from Compose,** with Substrate's own `deploy/compose.yaml` as the
   test (decoded from the map, it should match what runs; the running state encoded back).
3. **M-17's gate at the model endpoint**, then M-17's first experiment (the handoff, 2026-11-22).
4. **The telemetry collector and a process runtime** (process-compose first), picked with the `research` skill, as
   the second decoder target.
5. Then, as before: the live map and avatar page (S-158), the business distribution, process KPIs and one real
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
- How blocks' plans and the kernel refer to P-Plan, whose licence is CC BY-NC-SA 2.0 (non-commercial; S-174).
- Confirming the kernel's D-101 (the content framing) once the catalog entry has proved it or not.
- Whether LFM3 (LFM Open License v1.0) may be the recommended fast model (S-169).
