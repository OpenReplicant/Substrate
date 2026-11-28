# Plan

The one current plan (S-124, 2026-11-17). It replaces the plans in `docs/archive/` (the spec and its build plan,
the experiment-first direction, the handoff, the task briefs); those are kept as history and are not to be worked
from. Every default and its reason is still in `DECISIONS.md`.

## What Substrate is now (S-209 to S-214, 2026-11-24)

**The default distribution:** an agent harness (Claude Code first) configured to get things done with the kernel
and Morphogen, interactively, with Substrate's optional parts installed onto the kernel. Morphogen is the kit (map,
research, catalog, optimise, on files); the kernel is the layer above it; MetaSoar is the research. The shape is
`docs/framework.md`, every part and where it goes is `docs/parts.md`. The steps table further down is the history
of how the current parts came to be; what comes next is "The re-cut" just below.

## The re-cut, and what comes first (S-209, S-210, 2026-11-24)

The owner: "the thing that I wanted to make substrate or at least some project dedicated to was the idea of building
a map and maintaining it along with optimization targets", and "the business opportunity right now is in morphogen
mapping organizations and systems for smb's to identify the optimization opportunities and present those as
implementation projects". Mapping, research, cataloguing and optimising become one file-based kit in Morphogen, on
the harness the user chooses, with no database (S-209, the proposal `docs/morphogen-kit.md`); the kernel ingests
its files when indexing and traversal are wanted; Substrate is what runs on both. These steps come before the
product cut and "Next, in order", which are now Substrate's running system, built after them.

1. **Done 2026-11-24 (Morphogen #102, #103, #104; S-217): the skills, the format, cells in the catalog; a made-up firm mapped with no kernel, options for one role, one opportunity judged (`demos/fernhill`).** **The kit, in Morphogen, by pull request:** the `map`, `catalog` and `research` skills moved there and rewritten
   for files, Morphogen's and Substrate's `map` merged into one, the catalog entry's format (interfaces, adjustable
   parameters, licence, docs link) in its `schemas/`, its README saying what it is now. Done when the plugin, with
   no kernel running, maps a made-up firm from its documents and an interview into entity files, catalogues the
   options for one role, and drafts cells for one opportunity.
2. **Built 2026-11-25 (S-216): the plugin repinned, the three skills removed, Morphogen reads Substrate's catalog with no errors; `scripts/check.sh` waits on the stack being up.** **Substrate uses the plugin like any user:** its three skills removed from `.claude/skills/`. Done when
   `scripts/check.sh` passes and mapping Substrate itself works through the plugin.
3. **Done 2026-11-24 (Morphogen #104, S-217): `demos/fernhill/run.sh` went from the material to the report unattended, all eight checks of `check.py` passing; the report is `demos/fernhill/engagement/report.md`.** **The engagement, on a demo SMB:** from the firm's material to a report of optimisation opportunities, each
   written up as an implementation project (what changes, the target and its measure, the options catalogued, the
   cost and risk). Done when a scripted run goes from the material to the report without help.
4. **Prospecting:** the same mapping on public sources about a firm, giving a first opportunity list before a first
   call. Done when it runs on three real firms and the owner judges the lists worth opening a conversation with.
5. **The kernel above it, when wanted:** the kit's files ingested by the kernel's `encoder-backstage` and searched
   and traversed there. Done when a demo firm's map reads the same in the kernel as in its files.

The business itself (offer, pricing, prospect lists) is worked in a session of its own (S-188 c), once step 3 has a
report to show.

**Proposed 2026-11-27 (S-223): the manager agent,** a lean session that knows every project and hands work to
workers, built on the parts of `docs/parts.md`'s step 2. The design, its build order and the owner's questions are
`docs/manager-agent.md`; nothing is built until the owner answers them.

**Amended by S-211 (2026-11-24):** Substrate is a default configuration, not a product: a harness set up to use the
kernel and Morphogen. Work goes to Morphogen (step 1 above) and the kernel first: its parts become kernel modules or
standard module types (`docs/parts.md`, whose order replaces steps 2 and 5 above; S-212: the optional modules stay in this repository, written to the kernel's module contract, and make up the default distribution with the kernel's core); the test of the bet is step
3, one implementation project on a demo SMB carried out under the kernel's gates.

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

Self-levers beyond budget and model choice, and the other layers in `docs/archive/framework-s185.md`, come as these steps
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
  every link. (The voice front end's loop and M-17's ladder were listed here; they are distribution components now,
  S-186.)
- **The kernel's boundary is the kernel's own decisions:** queues belong to a distribution in its own database
  (D-94 c, superseded by the kernel's D-126: one database, the kernel's, S-190); signals and telemetry are observations, not claims ("a
  measurement is not content anyone wrote", D-101); what is worth knowing crosses as claims and items through an
  encoder (`encoder-substrate`); `propose`-gated actions are meant to reach the kernel's review lane, so a person
  approves in one place.
- **Observability:** OpenTelemetry where the parts already speak it (the gateway, the runtimes, our processes), an
  OTel Collector picked with the `research` skill, traces to a viewer and metrics to Prometheus, which the kernel's
  `observer-prometheus` turns into observed claims; a component's card carries measured latency and cost.
- **Agents:** the orchestrator is an ordinary harness (S-185); sub-agents are harness sub-agents, OpenEnv
  environments or MCP components (`docs/archive/framework-s185.md`, "Slots"). The one assistant of S-181 (the voice front end
  and one loop over model rungs) is the assistant distribution's design (S-186). `scripts/trials/harness/candidates.json`
  holds the surveyed harnesses.

## The ladder (S-178 to S-183, placed by S-186)

The multi-response ladder (System 1 at the model endpoint: compiled skills, then the fast, slow and cloud models,
chosen by a decider that learns from outcome-labelled experience) is a **distribution component**, built on OpenEnv
(S-186), not part of Substrate. Its design stands in S-178 to S-183, as an input to the new assistant and not a commitment; its code was removed
(S-194, S-195), and git keeps it.

## The product cut (S-201, 2026-11-23)

The owner: "let's get this to a state where it could be presented as a product, and i could use it as a tool in
consulting"; "the polish can be added later". The product is what the consulting pilot needs (`docs/research/Object
environments prior art.md`: a five-day, fixed-price "process map plus one gated automation" for firms of 10 to 200
people): one instance per client, a desktop the consultant and the client sign in to, an assistant to talk to in it,
the client's system mapped with evidence, and one automation whose writes wait for a person's approval. These steps
come before the list below; where they overlap, they name its step.

1. **Done 2026-11-23 (S-202).** **One database, the kernel's** (step 4 below): the `env` schema into the kernel's database, `substrate` dropped.
2. **Built 2026-11-23 (S-205, S-206): the MCP router, the desktop's conversation and the Assistant window, `scripts/assistant.sh`; the owner's first conversation held 2026-11-24 (S-208): it works and was convoluted, so left: kernel #138 merged (reads pass the router), a chat interface from a library picked with the `research` skill (the owner: "there's a library for this kind of interface"), and the assistant run without its narration in a terminal.** **The desktop as an environment, and the assistant's first use** (S-200's next idea): the person's messages and
   actions in the desktop are signals; the assistant (Claude Code behind the channel, S-143) answers through
   actuators: a message, a notification, a window it opens to show something (`free`), a question that waits for the
   person, and anything that changes something behind `propose`, decided in the desktop's Review. A chat window in
   the shell; structured events, not screenshots. The same environment served as OpenEnv for tests and simulation.
   Done when the owner talks to the assistant in the desktop, it shows him a map in a window, and a change it proposes
   waits for his approval there.
3. **The pilot, end to end, on a demo firm:** the kernel's interview and process maps (its D-115 to D-119) and
   Substrate's `map` and `catalog` skills on a made-up firm of about 30 people (documents, one event log, an
   interview); the assistant finds a step worth automating, builds it as a gated automation, a person approves its
   writes in the desktop, and the evidence (claims, quotes, the approval) is a report. Done when a scripted run goes
   from an empty instance to the report without help, and the same run works on a real firm's material.
4. **An instance per client** (step 7's bootstrap, cut to what a client needs): one command brings up a named
   instance on a laptop or a small server (its own `.env`, secrets, volumes, ports), with backup, export and restore,
   and an upgrade path; nothing of one client in another's instance.
5. **Signing in for a hosted instance** (S-200's SSO idea): an identity provider picked with the `research` skill
   behind Caddy's `forward_auth` for every app; OIDC where an app supports it; header sign-in or the app's own login
   off where it allows; a password manager's autofill as the last resort, never the proxy holding passwords. The
   kernel's person logins mapped from it (the kernel's O-6, a kernel decision). TLS on a public host name.
6. **Presentable:** README and a getting-started page read cold (step 8), a demo script and a recorded run of step
   3, a one-page description of the offer. Then the business session (step 10).

The owner's to decide before step 6: the product's name, the licence and whether the repositories go public, and
whether a client's instance is hosted by him or runs on the client's machine.

## Next, in order (2026-11-23)

Done from the 2026-11-22 list: the catalog entry (S-176), compose into the kernel and back (S-177), the decider trial
and experience (S-179, S-183).

1. **Done 2026-11-23 (S-192): all seven points pass; gates stay a `propose` tool (fastmcp caps `mcp` below 2, so no `input_required` yet).** The OpenEnv spike (S-184): `openenv` 0.12.0 in the tools image (or a trial container), one Postgres-backed
   environment, and the seven points: (1) many agents' sessions share one live environment; (2) events reach a
   subscriber in production mode; (3) `reset` clones a template database fast enough; (4) Claude Code runs through
   the harness adapter; (5) against our model proxy via `ANTHROPIC_BASE_URL`, with an episode id in a header;
   (6) a skill's answer reaches Claude Code in a form its loop accepts; (7) a rubric's score attaches afterwards to
   every model call of its episode. Also: whether MCP's `input_required` (revision 2026-07-28) is final, for gates.
   Done when each point has a result line in `.state/trials/openenv/` and a row in `DECISIONS.md`.
2. **Done 2026-11-23 (S-193), but for verdicts on `main` once PR #22 is merged: plugin pinned, the catalog as its map, the `voice-route` cell judged end to end with model calls metered at the gateway.** Morphogen as the optimiser (S-185): update `~/Projects/Morphogen` from GitHub (it is rebuild 5 here; main is
   rebuild 7); install its plugin in the orchestrator's harness; one map skill (Substrate's writes the Backstage
   entities, Morphogen adds cells from them); one cell on Substrate's own configuration judged end to end. Changes
   to Morphogen go by pull request there (the `upstream` skill).
3. **Done 2026-11-23 (S-194 to S-197): the old assistant's code removed, not ported; envkit retired; the pins moved to what runs; no reader of the dropped `store` schema left.** Left for later steps: Substrate's own map in the kernel (Q10, from v1's import) still names removed parts (`store/`, `voice/`), which step 7's snapshot map replaces. The repository in its shape (S-185, S-186): Substrate keeps the stack, the skills, the channel, the catalog
   and the adapters; components and the judge (S-151) gave way to Morphogen.
4. **Done 2026-11-23 (S-202): `env` in the kernel's database, `substrate` dropped (backed up); Bifrost's `gateway` database stays apart.** **One database, the kernel's** (S-190): the kernel defines the schemas and the ways of doing things, and Substrate
   follows them, so the `env` schema (objects' live state, queues, gates, experience) moves into the kernel's
   database, by the kernel's D-126 superseding D-94 (c) (drafted on the kernel's branch `claude/one-database`). Then
   the `substrate` database is empty and is dropped (its retired `store` schema went on 2026-11-23, S-191). Bifrost's `gateway` database is a third party's private store and stays apart
   unless Bifrost can use a schema in the kernel's database (to check).
5. **The orchestrator's `orchestrate` and `optimize` skills**, hooks enforcing gates in the harness, and an **`rtfm`
   skill** (S-189) for every agent: assume what it knows about a library, tool, API or standard is out of date; find
   the manual for the exact version in use (the project's docs, `llms.txt`, the registry's page, a docs MCP server
   where one is trusted); ingest it into the kernel with its source and version, so it is searched and recalled by
   association and cited; and answer from it, not from memory. Rule 1 ("look it up, then pin it") as a skill.
6. **Everything else runs on top of the settled shape** (S-187): each distribution (the new assistant, started from
   scratch once the owner names its first two or three uses, S-194; the SMB Foundry's first cut), MetaSoar's experiments and every test suite run against Substrate through its contracts only. Done
   when `scripts/test.sh` passes, each distribution comes up from its own folder, and MetaSoar's worlds run as OpenEnv
   environments.
7. **The bootstrap instance** (S-187): what a new Substrate instance starts with, so the orchestrator knows itself
   from the first run: a **snapshot map** of Substrate's own parts (the `catalog/` Backstage entities, the stack's
   compose file in the kernel, S-176, S-177), **catalogs** of the candidates already researched for each intended
   component (models, the gateway, harnesses, deciders, the environment standards; with their measurements), the
   vocabularies (S-175), **Morphogen cells** for Substrate's own configuration, the default gates and privacy
   rules, the skills, **agent-facing documentation** (S-189: more than skills: how the system works, its contracts,
   each tool and each part, written for an agent to read and loaded into the kernel for recall, with the manuals of
   the parts' exact versions fetched by `rtfm`), and a first task: map yourself, check the map against what runs. Loaded by one command into
   an empty kernel. Done when a fresh machine's instance answers "what are you made of, and what could replace
   each part?" from its own store.
8. **A second pass over the documentation** (S-187): README, `docs/framework.md`, the skills and each distribution's
   README read cold by someone new; every concept explained once, where it is used.
9. **M-17's experiment** (S-186, MetaSoar), on OpenEnv: a task-family environment, a model proxy in the Anthropic
   format, rubric scores as outcomes, the frozen blind run (S-179). The ladder's code is gone (S-195); if the new
   assistant takes the ladder's design (S-178 to S-183), it is rebuilt there, not restored.
10. **One notion of a map, and things opened in their viewers** (S-207; found trying the assistant, S-206). The
    kernel's Map view draws one map (every `org:` and BBO claim as one graph); Substrate has many maps (each thing
    mapped, with its parts, roles and interfaces). A **map becomes an item** whose parts hang off it, many per store,
    **one marked self** (the system mapping itself); the kernel's self-model (modules, slots) becomes that self map,
    not a notion of its own. In the desktop, **the launcher holds apps only** (search, review, the graph, the framed
    apps); the map, BPM and modules views stop being launcher entries (and the "kernel" group goes) and become **the
    viewers of their content types**: opening a map or a process shows it in its type's viewer, the Map viewer with
    a picker that starts on self. A kernel change by pull request (the owner's) and its decision there; here the
    desktop's launcher and the assistant's `desktop_show`. Done when the self map opens from the launcher with
    Substrate's parts in it, and a second map opens in the same viewer.
11. **The SMB Foundry and other business opportunities** (S-188 c): in **a session of their own**, without the code
    in context, **as soon as steps 6 to 8 are done**. The first customers are design partners and the most
    valuable, paid or not. Starting point: `docs/research/Object environments prior art.md` (a five-day "map and
    one gated automation" pilot).

Later, built on all of this: mapping and modelling things beyond software, agents and organisations (the owner's
original "map anything" idea, `owner-vision` in S-117's terms).

The telemetry collector and a process runtime (the old step 4) wait until a step needs them.

## Deferred

Morphogen R&D (statistics, the judge's own gateway and meter, the queue, GitHub Actions, the evidence log), the
case-and-scorer kit and the environment contract's generalisation, held-out cases by script, the paper catalog's
publication and reproductions, the hosted mapper and hosted judging, the slot model
(`docs/archive/slots.md`).

## The owner's to decide

- Which game comes first and which embodied environment after it (the steps table's 9 and 10; a games distribution now).
- Rotating the Postgres password.
- The licence and whether the repository goes public.
- Whether a Business-Source-licensed part (Nomad) may ever be a default; recommended no (S-173).
- When to migrate kernel v0's P-Plan IRIs to PROV-O and the profile's terms (S-175; a kernel change).
- Confirming the kernel's D-101 (the content framing) once the catalog entry has proved it or not.
