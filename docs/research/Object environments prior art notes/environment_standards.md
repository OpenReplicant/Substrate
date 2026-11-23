# Environment and object-interface standards compared with the Substrate design (as of 2026-11-23)

Method note: facts below were read from the cited page in this session (WebFetch returns a model-written summary of the page, so quoted detail is only as good as that summary). Items I could not fetch are in Gaps. "Inferences" are mine, not sourced.

## 1. OpenEnv (reset/step/state/close, manifests, governance, RFCs, harness integration)

### Takeaway
OpenEnv is a BSD-3 episodic Gym-style protocol (reset/step/state over WebSocket, containers, MCP tools at /mcp) governed by a multi-company committee and still "early development". It already has a "production mode" that serves MCP tools of a persistent service without episode control, and RFC 005 runs an unmodified Claude Code inside an environment, so a persistent live Substrate environment can expose an OpenEnv interface cheaply, but only as a thin adapter; its object/gate/event model is not part of OpenEnv.

### Cited Findings
- Licence BSD 3-Clause; "early development, so APIs may still change"; reset/step/state sync or async over WebSocket; each environment is a Docker image; CLI `openenv init/validate/push/serve/import`; ~2.9k stars, 40+ environments, integrations with TRL, Unsloth, SkyRL, etc. — [GitHub meta-pytorch/OpenEnv](https://github.com/meta-pytorch/OpenEnv)
- Governance: multi-company Technical Committee since June 2026 (Meta-PyTorch, Reflection, Nvidia, Microsoft, Prime Intellect, Mercor, Fleet AI, Modal, Unsloth, BenchFlow, Hugging Face); biweekly meetings; RFC loop; Ben Burtenshaw acts as BDFL early on; no formal foundation governance in the file — [GOVERNANCE.md](https://github.com/huggingface/OpenEnv/blob/main/GOVERNANCE.md) (page dates internally inconsistent per the fetch).
- Maintainers' post of 2026-10-22 says they are "joining AAIF" (Agentic AI Foundation) and a public AAIF proposal seeks a vendor-neutral home; not yet confirmed as completed — [AAIF blog](https://aaif.io/blog/training-agents-for-real-world-tasks-with-openenv)
- June 2026 HF post: OpenEnv is a protocol layer (publish/deploy/consume), Gymnasium-style API over HTTP/WebSocket in Docker, "MCP as a first-class citizen"; roadmap includes harness integration and env auto-validation; says nothing on live/persistent environments — [HF blog](https://huggingface.co/blog/openenv-agentic-rl)
- Repo location is inconsistent across sources: meta-pytorch/OpenEnv, huggingface/OpenEnv, and github.com/openenv/OpenEnv all appear; the HF post says it now lives at huggingface/OpenEnv — [HF blog](https://huggingface.co/blog/openenv-agentic-rl), [GitHub](https://github.com/meta-pytorch/OpenEnv)
- RFC index (rfcs/ directory): 000 design principles/roadmap, 001 basic abstractions, 002 framework spec, 003 MCP support (traditional tool calling), 004 rubric/reward, 005 agentic harness integration (OpenClaw, Claude Code), 006 harness interception/token capture, 008 env auto-validation, 010 env-token world modelling, 011 versioned env metadata / ARD interchange, 012 Harbor, 014 environment services (brokered, budgeted external access). 007, 009, 013 not in the listing. Lifecycle: In Review, Accepted, Implemented, Rejected, Superseded — [rfcs dir](https://github.com/meta-pytorch/OpenEnv/tree/main/rfcs), [rfcs README](https://raw.githubusercontent.com/meta-pytorch/OpenEnv/main/rfcs/README.md)
- Numbering conflict: the HF blog calls RFC 003 "encapsulation of MCP tools through environment abstraction" and lists 006 as external rewards and 007 as tasksets via HF datasets; the repo index differs (006 = harness interception). Treat numbers as unstable — [HF blog](https://huggingface.co/blog/openenv-agentic-rl) vs [rfcs dir](https://github.com/meta-pytorch/OpenEnv/tree/main/rfcs)
- I did not find a "RFC 0054" in any source.
- MCP in OpenEnv: dual boundary. Gym control plane (`/ws`, reset/step/state) for the trainer; MCP tools over `/mcp` for agents. In simulation, MCP calls flow through `step()` as `ListToolsAction`/`CallToolAction`. `reset`, `step`, `state`, `close` are reserved tool names. RFC 003 "proposes MCP as the standard interface for all agent-facing actions" and is still In Review; only echo_env, finqa_env (and calendar_env via wrapper) are MCP-backed, most others use custom action types — [HF docs: MCP environments](https://huggingface.co/docs/openenv/main/en/tutorials/mcp-environment)
- Production mode: "serves the environment's MCP tools directly to an agent or another client, with no episode control"; `/reset`,`/step`,`/state` are not registered; `/ws` still registered (restrict it); mode-aware tools; "simulation mode models trajectory time, production mode models service time" — [HF docs: simulation vs production](https://huggingface.co/docs/openenv/main/en/guides/simulation-vs-production)
- RFC 005 (In Review; created 2026-02-16, revised 2026-10-07): `HarnessEnvironment` wraps an external harness (Claude Code, OpenClaw) running its own loop; each `step()` is one conversational turn; tools injected through a localhost streamable-HTTP MCP bridge written into the harness's MCP config; no LLM-call interception or proxy in this RFC (LLM_REQUEST/LLM_RESPONSE events exist but are unpopulated); no concurrent sessions; network isolation not enforced; Claude Code adapter merged (#1291), OpenClaw adapter not — [RFC 005](https://github.com/huggingface/OpenEnv/blob/main/rfcs/005-agentic-harnesses.md)
- Claude Code tutorial: runs `claude -p --input-format stream-json`, built-in tools disabled (`--tools ""`), environment tools via `--mcp-config`; `ANTHROPIC_BASE_URL` in `HarnessConfig.env_vars` can point it at an Anthropic-compatible endpoint — [HF tutorial](https://huggingface.co/docs/openenv/main/en/tutorials/claude-code-harness)
- Harness comparison: white-box (trainer owns the loop), black-box via Harbor/RFC 006 where "a proxy records every model call it makes" to build a `TrainingTrace` (token ids, logprobs, against vLLM or SGLang), and agent-inside-environment (RFC 005). Only Harbor records tokens — [HF: Harnesses in OpenEnv](https://huggingface.co/docs/openenv/main/en/tutorials/harnesses)
- A GitHub issue asks whether RFC 005 is still in effect and notes `openenv.core.harness` seems loosely related; no maintainer answer seen — via [search result](https://gh.r-mj.com/huggingface/OpenEnv/issues/696) (secondary mirror).

### Inferences
- Cheapest compatible path: an OpenEnv "production mode" server (`/mcp`) whose tools are the Substrate gated actions, plus an optional simulation-mode shim (`reset` = snapshot/branch of the DB or a fresh schema, `step` = apply action and advance, `state` = read). A single live shared database does not fit `reset`/episode semantics; reset would need a per-episode schema or a transaction/branch copy.
- OpenEnv's harness-proxy idea (RFC 006/Harbor: proxy on the model endpoint recording tokens) matches Substrate's gateway-proxy design; Substrate could emit the same trace shape for training a System 1.
- OpenEnv's gating is only "reserved names" and a note to restrict `/ws`; it has no free/propose/deny notion, so Substrate's gates would be an extension surfaced as tool errors or `input_required`-style results.
- Risk: spec churn (RFC numbers disagree, repo moves, early-development warning). Adopt by thin adapter, do not build the core around it.

### Gaps
- Could not read RFC 002/003/006 text directly (404 on guessed paths); statuses of 001-004 not confirmed.
- No source for "RFC 0054" or for the manifest file format (the README summary did not describe a manifest); `openenv.yaml` details unverified.
- Whether the AAIF move completed is unconfirmed.

## 2. W3C Web of Things Thing Description

### Takeaway
TD 1.1 is a W3C Recommendation (Dec 2023) whose properties/actions/events/forms/security model maps almost one-to-one to Substrate's object model, and TD 2.0 is only a First Public Working Draft (Nov 2025). It is the best candidate to expose objects (as generated Thing Descriptions), with MCP as the transport LLMs use.

### Cited Findings
- TD 1.1: W3C Recommendation, 5 Dec 2023, supersedes TD 1.0; defines properties (read/write/observe), actions, events, forms (hypermedia controls serialising protocol bindings), security schemes (nosec, basic, digest, bearer, apikey, oauth2, combo, auto), JSON/JSON-LD, Thing Models; W3C Software and Document licence applies — [TD 1.1](https://www.w3.org/TR/wot-thing-description11/)
- TD 2.0: First Public Working Draft 4 Nov 2025; no newer draft found; a proposed 2026 WG charter lists it as a further iteration; WoT documentation still lists TD 1.1 as current — [TD 2.0 FPWD](https://www.w3.org/TR/2025/WD-wot-thing-description-2.0-20251104), [proposed charter](https://www.w3.org/2026/07/wot-wg-2026.html), [WoT docs](https://www.w3.org/WoT/documentation/)
- node-wot (Eclipse Thingweb): dual EPL-2.0 or W3C Software and Document Licence; HTTP(S), CoAP(S), MQTT full; WebSocket server only; OPC-UA, NETCONF, Modbus, M-Bus client only; Node 20+; ~196 stars; 3,076 commits — [node-wot](https://github.com/eclipse-thingweb/node-wot)

### Inferences
- Mapping: Substrate property = TD property (observable = subscribe); action = TD action; event/pgmq topic = TD event; gate (free/propose/deny) has no native TD field and would be an extension vocabulary term or a form-level annotation; Postgres roles/RLS map to security definitions (bearer/oauth2) plus an extension for per-affordance policy.
- Traits-not-types fits TD Thing Models (templates) plus JSON-LD `@type` arrays; nesting environments maps to links/`tm:` composition rather than a native construct.
- Generating TDs from the object tables is low cost and adds discoverability for non-LLM clients; node-wot as a runtime is optional (Node dependency; Substrate rule of nothing on host means a container).

### Gaps
- Did not read TD's full text beyond the first 100k characters; did not verify TD 2.0 feature list.

## 3. Agents & Artifacts (A&A) and CArtAgO

### Takeaway
A&A is the closest academic precedent for "environment as programmable first-class objects": artifacts offer operations and observable properties, emit signals, live in workspaces, and agents focus on the artifacts they care about. Copy the vocabulary and focus semantics; skip the BDI/Jason coupling.

### Cited Findings
- Ricci, Piunti, Viroli, "Environment programming in multi-agent systems: an artifact-based perspective", Autonomous Agents and Multi-Agent Systems 23(2):158-192 (2011): environment as first-class programmable abstraction, based on the A&A meta-model, implemented by CArtAgO — [UniBo record](https://cris.unibo.it/handle/11585/108512)
- Artifacts live in workspaces; operations form the usage interface, observable properties report state, signals are a separate percept for events; an agent "focusing" on an artifact receives its property updates (in Jason, mapped to beliefs) and perceives signals; a predefined workspace artifact handles creating, looking up, linking, and focusing artifacts — secondary sources: [JaCaMo/CArtAgO summary search](https://arxiv.org/pdf/2207.09708), [EMAS 2023 paper](https://emas.in.tu-clausthal.de/2023/papers/EMAS_2023_paper_3263.pdf), [CArtAgO by example (unofficial copy)](https://www.scribd.com/document/385336024/cartagoByExamples-pdf)

### Inferences
- Direct matches: your "agents subscribe to the streams they want" = focus; observable properties = columns with change notification; signals = pgmq events; workspace = environment that nests. Copy: focus as an explicit subscription row, a distinction between state (observable property, replayable) and signal (transient event), and operations that can block/fail with feedback.
- Differences: A&A artifacts are typed classes in code; yours are trait-based and data-driven. A&A has no permission gate (propose/approve); that is your addition.

### Gaps
- Official CArtAgO/JaCaMo docs and licence not fetched (SourceForge redirect not followed); licence unverified here.

## 4. MCP as an object model, and the MCP Registry

### Takeaway
MCP gives you tools (actions), resources with URIs and subscriptions (observable properties), prompts, and a registry for discovery; resource subscriptions are being replaced in the 2026-07-28 revision by one `subscriptions/listen` stream. It is the right joining surface for tools and for LLM-facing views of objects, but it has no object identity beyond URIs and no gate semantics.

### Cited Findings
- 2025-11-25 resources: URI-identified; `resources/list`, `read`, templates (RFC 6570); optional `subscribe` and `listChanged` capabilities; `notifications/resources/updated`; annotations (audience, priority, lastModified); resources are "application-driven" — [MCP resources spec](https://modelcontextprotocol.io/specification/2025-11-25/server/resources)
- 2026-07-28 revision changelog (as served at that URL; whether it is final or draft was not stated on the page, and a search summary called it "draft"): removes protocol-level sessions and the initialize handshake (stateless, version and capabilities in `_meta`); adds `server/discover`; replaces `resources/subscribe` and the GET endpoint with `subscriptions/listen`; tasks moved to an extension with polling (`tasks/get`, `tasks/update`); Multi Round-Trip Requests (`input_required` results) replace server-initiated sampling/elicitation; deprecates Roots, Sampling, Logging; `ttlMs`/`cacheScope` on list/read results; OpenTelemetry trace context in `_meta`; Client ID Metadata Documents over Dynamic Client Registration; feature lifecycle with 12-month deprecation window — [changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog)
- MCP Registry: preview launched 2025-09-08, API freeze for v0.1 from 2025-10-24, "breaking changes or data resets may occur", servers published with `mcp-publisher`; I did not confirm a GA date — [registry repo](https://github.com/modelcontextprotocol/registry)
- MCP is a founding project of the Agentic AI Foundation (Linux Foundation, 9 Dec 2025) with goose and AGENTS.md — [Linux Foundation](https://www.linuxfoundation.org/press/linux-foundation-announces-the-formation-of-the-agentic-ai-foundation); one arXiv paper's claim that AAIF also hosts A2A is not confirmed by this source.

### Inferences
- MRTR `input_required` is a natural carrier for the `propose` gate: a tool call returns "input required: human approval", and a retry carries the approval. Also matches OpenEnv's tool-error channel.
- Stateless MCP matches a database-as-state design: the server holds no session, state lives in Postgres.
- Expose each object as resources (`substrate://object/{id}`), with change feeds via `subscriptions/listen` mapped from pgmq; expose actions as tools; publish the MCP server entry in the Registry only if a public server is wanted.
- Plan for the 2026-07-28 migration (subscribe removal) if building on resource subscriptions.

### Gaps
- Final/draft status of 2026-07-28 unverified; MCP Registry GA status and licence not confirmed; MCP tools spec page not re-read.

## 5. Other 2025-2026 interface standards (CUBE, Agent Spec, harness papers, A2A, AsyncAPI, CloudEvents, ROS 2, Home Assistant, Gymnasium)

### Takeaway
Only A2A (stable v1.0), CloudEvents (CNCF graduated) and AsyncAPI are mature; CUBE, Agent Spec and OpenEnv are young and benchmark/portability-oriented. Adopt CloudEvents for event envelopes and borrow A2A's task states for long-running actions; ignore Agent Spec and CUBE except as export targets; Gymnasium only matters if a training adapter is needed.

### Cited Findings
- CUBE (Common Unified Benchmark Environments): position paper by Lacoste et al., arXiv 2603.15798 (Mar 2026), CC BY 4.0; "protocol standard built on MCP and Gym" with task, benchmark, package, registry layers — [arXiv](https://arxiv.org/abs/2603.15798). The AI Alliance package is alpha with Tool, Task, Benchmark, Observation, Action interfaces; ServiceNow principal developer — [cube-standard](https://pypi.org/project/cube-standard/), [search summary](https://the-ai-alliance.github.io/cube-standard/about)
- Open Agent Specification (Oracle): declarative framework-agnostic language for agents and workflows; SDK PyAgentSpec, reference runtime WayFlow; dual UPL-1.0 / Apache-2.0; arXiv 2510.04173 — [GitHub](https://github.com/oracle/agent-spec), [arXiv](https://arxiv.org/html/2510.04173v3)
- arXiv 2610.40917 (Gertler, Novelli, Floridi, 29 Oct 2026) "Towards Portable Specification of the Agent Harness": eight harness components; proposes a portable specification recording which model ran in which harness; harness as "a versioned part of the system" — [arXiv](https://arxiv.org/abs/2610.40917)
- arXiv 2606.10106 (de Macedo, 8 Jun 2026): necessary and sufficient conditions for an agent harness, applied to Claude Code, Codex CLI, Aider, Cline, OpenHands, SWE-agent — [arXiv](https://arxiv.org/abs/2606.10106)
- arXiv 2608.23953 (Dai, 25 Aug 2026): three harnesses converge on a standard loop, an append-only replayable session record, model quirks as data, progressive disclosure, explicit extension points; the one non-converged axis is external verifiability (tamper-evident record) — [arXiv](https://arxiv.org/abs/2608.23953)
- A2A: v1.0.0 is latest; AgentCard, Task (SUBMITTED, WORKING, INPUT_REQUIRED, AUTH_REQUIRED, COMPLETED, FAILED, CANCELED, REJECTED), Message, Artifact, Part; streaming and push webhooks; `A2A-Version` header — [A2A spec](https://a2a-protocol.org/latest/specification/). Donated to the Linux Foundation 23 Jun 2025; 150+ organisations; v1.0 dated March/April 2026 with sources disagreeing (an arXiv paper says Jan 2026) — [LF press](https://www.linuxfoundation.org/press/a2a-protocol-surpasses-150-organizations-lands-in-major-cloud-platforms-and-sees-enterprise-production-use-in-first-year)
- CloudEvents: CNCF graduated 25 Jan 2024; 1.0.2 current stable, 1.0.3 in working draft — [CloudEvents spec](https://github.com/cloudevents/spec), [CNCF](https://cncf.io/announcements/2024/01/25/cloud-native-computing-foundation-announces-the-graduation-of-cloudevents)
- AsyncAPI 3.0.0: channels, operations (send/receive), messages, servers, bindings; Apache-2.0; 3.1.0 also listed — [AsyncAPI 3.0.0](https://www.asyncapi.com/docs/reference/specification/v3.0.0)
- Home Assistant entity model: entities inherit `Entity` via platform classes; `state` written to a state machine; attributes; stable `unique_id` for the entity registry; `device_info` links to a device; unavailable shows as `unavailable` — [HA developer docs](https://contributors.home-assistant.io/core/entities/entity-class/). Services and `state_changed` events were not on that page.
- Gymnasium 1.x: `reset(seed, options)` returns (obs, info); `step` returns terminated and truncated separately; 1.0 changed vector autoreset — [Gymnasium migration guide](https://gymnasium.farama.org/introduction/migration_guide/), [v1.0 release](https://farama.org/Gymnasium-v1.0)
- ROS 2: Jazzy is LTS to May 2029; Kilted (May 2025) support ends Nov 2026 — [Jazzy release](https://docs.ros.org/en/jazzy/Releases/Release-Jazzy-Jalisco.html), [Kilted](https://docs.ros.org/en/kilted/Releases/Release-Kilted-Kaiju.html). The topic/service/action/parameter concept page was blocked (Anubis); I rely on general knowledge, not a cited source, for that mapping.

### Inferences
- CloudEvents: use as the envelope for events in pgmq/the append-only record (id, source, type, time, subject, data); cheap, graduated, and gives Substrate events a standard export for free. 
- A2A: expose a Substrate agent object as an A2A server (AgentCard from its trait/card, Task states from a proposed action's lifecycle: propose -> INPUT_REQUIRED -> WORKING -> COMPLETED/REJECTED). Optional, because A2A is agent-to-agent while your agents share a database.
- Home Assistant is the best practical precedent for an entity registry with stable ids, state plus attributes, device grouping, and availability; its conventions (unique_id, availability) are worth copying.
- ROS 2 (by general knowledge, uncited): topics = streams, services = request/response, actions = long-running goal/feedback/result, parameters = per-node config; the "action with feedback and cancel" shape maps to propose-then-run actions.
- Harness papers: 2608.23953's finding that tamper-evident external verifiability is the unconverged axis aligns with your append-only record; 2610.40917's "harness as versioned part of the system" supports recording harness/model per run in the record. Neither is a standard to adopt.
- Agent Spec and CUBE: ignore as core; export of an agent's definition to Agent Spec is possible later.

### Gaps
- ROS 2 concept docs, HA services/events, PettingZoo licence, Gymnasium licence, CUBE reference implementation licence, and the A2A security sections were not verified. A2A date conflict unresolved.

## 6. Any existing system combining DB-as-environment, object actions, gates, and harnesses joining via a model-endpoint proxy?

### Takeaway
I found no single system that combines all of these. Pieces exist separately: Postgres RLS for agent permissions, blackboard testbeds, SpacetimeDB-style database-as-backend, and OpenEnv/Harbor's model-call proxy for token capture; no source found with a permission gate of free/propose/deny over object actions with harnesses joining unmodified.

### Cited Findings
- Search found Postgres row-level security guidance for agents (one role per agent; table owners bypass RLS unless FORCE ROW LEVEL SECURITY; unique/foreign-key constraints can leak) and a pgEdge article describing an action ledger in Postgres with RLS per agent role — [pgEdge](https://www.pgedge.com/blog/going-rogue-autonomous-ai-agents-and-postgres), [secondary guide](https://agentsecurityreview.com/posts/postgresql-permission-boundaries-for-database-connected-agents)
- Terrarium: blackboard testbed for multi-agent safety, privacy and security studies (arXiv 2510.14312) — [arXiv](https://arxiv.org/pdf/2510.14312)
- SpacetimeDB: tables plus transactional reducers, clients subscribe to queries and get incremental updates; reducers return no data; licence Business Source License 1.1 converting to AGPL v3 with linking exception (source-available, not permissive) — [SpacetimeDB FAQ via search](https://spacetimedb.com/docs/intro/faq), [NuGet licence](https://www.nuget.org/packages/SpacetimeDB.Runtime/2.8.0/License)
- OpenEnv/Harbor's proxy that "records every model call" the agent makes is the nearest analogue to the model-endpoint proxy — [HF: Harnesses](https://huggingface.co/docs/openenv/main/en/tutorials/harnesses)
- pgmq as an agent message queue and the phrase "database is the environment": no source found.

### Inferences
- The combination appears novel in what I could find, but absence of search hits is weak evidence; a search of GitHub for Postgres-backed agent frameworks was not done.
- SpacetimeDB's licence fails Substrate's permissive/LGPL rule for linking; as a fetched-at-setup separate container it would need S-146's process-boundary treatment, and its reducer model differs from Postgres RLS.

### Gaps
- No direct search of GitHub or arXiv for pgmq-based agent environments, Letta/other agent-memory frameworks, or LangGraph checkpoint-in-Postgres systems, which may be partial precedents.
