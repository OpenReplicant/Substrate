# The framework

What Substrate is built as (S-125). `docs/plan.md` says what is built next; this page says what shape it all
takes. Marked **decided** where the owner has agreed, **open** where not.

## In one paragraph

An **environment** is data in Postgres: streams of readings, the objects they are about, and the actuators that
can be acted on. With nothing else configured it is a **pass-through**: every event goes to an LLM harness
(Claude Code, on any model through the gateway), which acts through gated actuators, and everything is recorded.
From that record, the LLM **distills components** (reactive handlers for patterns in one event or several
aligned ones), each carrying a **card**: its intent, trigger, action, the cases it came from, its KPIs and tests.
A **judge** outside the author's reach tests the card on recorded cases the author never saw, and only then does
the component join the environment. What a component cannot handle goes back up to the LLM, and from there to a
person. Environments nest: a child is an object in its parent's environment. Workbench is where people watch
and decide.

## Signals and claims (decided, S-126)

- A **signal** is what a source reports: a reading, an event, a message, a snapshot, a transcript. It is kept
  whole and is no one's opinion; if it is wrong, the sensor is broken. Parsing a signal into fields leaves it a
  signal.
- A **claim** is an interpretation of one or more signals (or other claims) by an **interpreter** that answers
  for it: the LLM, a distilled component, or a person. It cites what it rests on, and can be wrong even when
  every signal is right, which is why it is reviewed, judged and retracted.

The test: anything that could be wrong for reasons other than a broken sensor is a claim. Streams carry signals;
the claim log holds claims; actions cite the claims that justify them (under pass-through the LLM may act straight
from signals, and records its interpretation as claims). Interpreters are components, so a distilled interpreter
has a card and its claims carry its name. A person's statement is their claim; the interview transcript is the
signal. Workbench today attaches a claim to every value, mechanical ones included: under this distinction a value
a parser wrote points to its signal with no interpreter, and only an interpretation names one (to be checked
against the schema).

**A claim's fields**, after Graphiti's data model ([graphiti](https://github.com/getzep/graphiti), Apache-2.0;
its `nodes.py` and `edges.py` read, S-129), with what it lacks added. Graphiti keeps raw input as episodes (our
signals) and facts as edges with an `episodes` list, and is bi-temporal: `valid_at` and `invalid_at` (when the
fact held), `created_at` and `expired_at` (when the store learned and dropped it). On a contradiction an LLM only
nominates candidates; code decides by dates. Kept: the four times, and "the model nominates, code decides". Not
kept: it overwrites an edge's times in place, has delete paths, records no interpreter, no confidence and no
review status, and links provenance by a list of strings. So a claim here carries `cites` (signals or claims, by
foreign key), `interpreter` (who, and which version of a component), `confidence`, `status` (proposed,
accepted, retracted) and `retracted_by`, and a change of belief is a new claim, never an edit. Graphiti has no
Postgres backend, so it is a model to borrow from, not a part to add.

## Three parts

| Part | Does | Is not |
| --- | --- | --- |
| **Substrate** | the environment, pass-through, the record, components and their cards, the hierarchy | a harness: Claude Code is the harness |
| **Workbench** | the UI and the store: the stream, the review lane, each component's card and verdicts, the map | a separate product (S-120) |
| **The judge** | an interface: a card and a candidate in, a verdict out, on cases the candidate's author cannot read | a framework; Morphogen is one filler of it, optional |

## The environment is data (decided)

Everything is in one Postgres, so the environment, the record and the judge's cases are the same data.

| Need | Mechanism |
| --- | --- |
| The source of truth | signals kept whole (pgmq's archive and the readings they become), and the claim log: claims (subject, property, value, the signals or claims cited, the interpreter, time, confidence). Append-only; a claim is retracted, never erased |
| Streams in | pgmq topics. A signal is published with `pgmq.send_topic` under a routing key `<env>.<stream>.<kind>` (dot-separated, so a child's keys sit under its parent's); logged queues, archived after handling, so a stream can be replayed |
| Sensing, in parallel | each subscriber (an encoder, a reactive handler, the LLM's channel) owns a queue bound to the patterns it watches (`pgmq.bind_topic`; `*` one segment, `#` any). Fan-out is pgmq's; no subscriber takes a message from another |
| Acting, in series | one pgmq queue per actuator, read by the one process that applies it. Who may write to it, and through which gate, is the arbitration |
| Gates | per action kind: `free` (applied), `propose` (into the review lane for a person), `deny`. Live work starts at `propose` |
| Escalation | a topic too: `<env>.escalate`, which the level above subscribes to |
| Views | pgGraph's projection, Ontop's SPARQL over the ontologies, full text, pgvector: read-only and rebuildable from the log |

Reactive logic runs in **handler processes**, not database triggers, so that each one is a component with a card,
a version and a verdict, and can be judged and rolled back. (Memgraph triggers over a property graph were the
earlier design; the graph is now a view of the claims, not the store.)

Raw readings are kept, so interpreting them into claims is itself a component: at first the LLM reads the raw
data and decides what it means; when it keeps deciding the same way, it writes an encoder with a card.

## Pass-through is the default (decided)

With no components, the environment hands every event to the harness. The harness is **Claude Code**, which
runs on any model the gateway serves and already has tools, MCP, hooks, skills, subagents, permissions and
context management; Substrate does not rebuild any of them.

- **In:** a Claude Code channel (an MCP server that pushes events into a running session) subscribed to the
  environment's topics.
- **Look around:** Workbench's MCP server, to query objects, claims and history.
- **Out:** actions written to actuator queues through MCP, under the gates; hooks and permissions enforce them.

Pass-through is useful on its own, and it is the **baseline every other layer is measured against**.

### The channel, as documented (read 2026-11-17, S-129)

From [channels](https://code.claude.com/docs/en/channels) and the
[channels reference](https://code.claude.com/docs/en/channels-reference). Research preview; the flag syntax and
protocol "may change", so the version that works is pinned when it is built.

- **Shape:** a local MCP server, spawned by Claude Code over stdio, declaring
  `capabilities.experimental['claude/channel']`, and sending `notifications/claude/channel` with `content` (the
  body) and `meta` (attributes; keys letters, digits and underscores only, others silently dropped). Claude sees
  each event as a `<channel source="..." ...>` tag; events queued during a turn arrive together on the next. Its
  `instructions` string tells Claude what the attributes mean.
- **No acknowledgement and no persistence:** a notification is fire-and-forget, and nothing survives a closed
  session. So the durable side is ours: the channel reads its pgmq queue with a visibility timeout and does not
  archive a message until Claude calls an `ack(msg_id)` tool (or acts on it); an unacknowledged message
  reappears and is delivered again.
- **Two-way:** replies and actions are ordinary MCP tools on the same server (or Workbench's).
- **Permission relay** (`claude/channel/permission`): Claude Code sends `permission_request` (`request_id`,
  `tool_name`, `description`, `input_preview`) and accepts `allow` or `deny` back; first answer wins. This can be
  where a `propose` gate meets the review lane: Workbench shows the request and a person's decision goes back
  through it. Anyone who can answer the relay can approve tool use, so it is declared only for an authenticated
  path.
- **Enabling it:** a server of our own needs `claude --dangerously-load-development-channels server:<name>`
  (a confirmation dialog; ignored with `-p` and through the Agent SDK), so pass-through runs as an interactive
  session kept open (tmux or a user service). Team and Enterprise organizations must set `channelsEnabled`.
- **Untrusted input:** "An ungated channel is a prompt injection vector." Every signal from outside is data,
  not instructions: the channel's `instructions` say so, senders are gated where a stream has senders, and
  actions stay behind the gates.
- **Unknown, to test first:** whether channels work when Claude Code runs on a non-Anthropic model through the
  gateway (`ANTHROPIC_BASE_URL`); the docs require a claude.ai login or a Console API key and say nothing of
  other endpoints. If they do not, pass-through on a local model needs another way in (a hook that injects
  pending events, or polling through a tool). Also unstated: rate limits, maximum payload, reconnects.
- **Known preview bug:** a server negotiating protocol revision 2026-07-28 does not register on the v2 MCP client
  runtime; pin the SDK's protocol revision.

## Components can be pipelines: adaptive perception (decided as a shape)

A component need not be a rule. When a stream has no handler, the LLM can build one: probe the signal, decide
what it is, and install a pipeline that turns it into something it can use. Example: a raw audio stream arrives
unhandled; the LLM samples it, and either pipes it to its own audio input if the model has one, or installs a
classifier (speech, music, noise) and, for speech, a speech-to-text model chosen from the catalog (the `research`
skill), writing transcripts as signals and what they mean as claims. Each stage is a component with a card, so
each can be tested, swapped for a cheaper or better one, and judged against the stage it replaces. The
environment's senses grow to fit its streams and its model: embodiment that adapts.

## Components and their cards (decided)

A component is a handler that subscribes to a pattern and does something: writes claims, proposes an action,
or escalates. Its kind may be a rule, a script, a model call, a Claude Code session, or a person. Components come
from the LLM distilling its own repeated decisions (or from a person), and each carries a **card**:

| Field | Says |
| --- | --- |
| intent | what it is for, in a sentence the owner can check |
| trigger | the pattern it fires on: one signal or claim, or several aligned in time |
| action | what it does, through which actuator |
| source cases | the recorded events it was made from, each with what the LLM or person did |
| KPIs | what it must hold to: agreement with what it replaces, cost per event, latency, override rate |
| tests | cases it must handle, and cases where it must not fire |

**Lifecycle:** proposed → judged → active at `propose` → `free` once trusted → demoted when it drifts (overrides
climb in the review lane). Every version is kept, so a component can be rolled back or compared against the LLM
it replaced.

**What CogRec shows, and what it lacks** ([arXiv 2512.24113](https://arxiv.org/abs/2512.24113), read in full,
S-129). A recommender: Soar handles what its rules cover; on an impasse, a summary of working memory goes to an
LLM (DeepSeek-V3), and the answer is parsed into a condition-action pair that Soar's chunking compiles into a
rule. It beat the best baseline by 4–9% on three datasets, and its rate of LLM calls fell to a low plateau as
rules accumulated; without chunking it stayed near the plain LLM. But no seeds, variance or significance tests
are reported, and learned rules are never tested, scoped or removed: they are "permanently internalized". That
is the gap the card and the judge fill. Taken from it: the escalation carries a structured summary of the
state, not the raw context; the answer is parsed into trigger and action before it becomes a component; and
the **rate of LLM calls per event** is a KPI of the whole environment, the number that should fall as it learns.

**Confidence is measured, not stated.** A component's confidence is the agreement the judge measured on held-out
cases, within the scope its trigger covers. The LLM gets an event when no trigger fires, when the event falls
outside what the component was judged on, or when the component has been demoted. (Cascade research finds
routing only as good as its quality estimate; this is how the estimate is earned.)

## The judge is an interface (decided; its filler is open)

A card and a candidate go in; a verdict comes out, with each KPI's result, the case counts, and pass or refuse,
appended to a log. What it needs beyond ordinary CI is two things: **cases the author cannot read** (a slice of
the record held by another role: Postgres row-level security, or a separate user for the stronger version), and
**comparison against the incumbent**, not pass/fail alone.

- **First filler:** a script run as the judge user, running the card's tests and the held-out slice.
- **Candidates for the runner** (rule 3, not yet searched): Inspect AI, promptfoo, DeepEval.
- **Morphogen** is frozen as an option behind the same interface (S-127). Its later overhaul, when the owner
  starts it, is toward a standard CI workflow built from components (a runner, held-out cases, a verdict log,
  statistics as a step) rather than one custom program.

## It is an actor model on Postgres (a description, not a runtime to build)

Each component is an actor: it owns a mailbox (its pgmq queue), handles one message at a time, and sends
messages (`send_topic`); the parent environment supervises its children, as an Erlang/OTP supervisor does. Two
differences from a pure actor model: state is shared, not private (the claim log is a blackboard every actor
reads), and an actor is judged before it runs live. So: actors for messaging, a blackboard for state.

What follows from that:

- **Borrow the semantics, not a runtime:** one mailbox per actor, per-mailbox order, supervision, retries with
  visibility timeouts. pgmq gives all of it; no actor framework is added.
- **Side effects must be idempotent:** a retried message re-applies its action. Writes to the database are
  transactional; anything outside (an email, an API call) needs an idempotency key on the actuator.
- **Postgres has a rate ceiling:** work-level events (tickets, messages, changes) are fine; high-rate sensor
  data is sampled or batched before it becomes a signal, or uses an unlogged queue where loss is acceptable.
- **Nearby tools** for durable steps on Postgres, if a component needs multi-step workflows:
  [Absurd](https://lucumr.pocoo.org/2025/11/3/absurd-workflows/) (SQL-only, works with pgmq),
  [DBOS](https://dbos.dev/blog/making-postgres-queues-scale), Hatchet. Chosen by the research skill when needed.

## The view: serializing the environment for the LLM (a component, tested per model)

What the LLM sees is a rendering of the environment, and how it is rendered changes results: one study found
up to 40% differences between plain text, Markdown, YAML and JSON on the same task, with no format best across
models ([He et al. 2024](https://arxiv.org/abs/2411.10541), OpenAI models only). It also decides cost, through
the prompt cache. So the **view is a component with a card**, like any other, and is judged per model and per
arrangement.

Its parameters:

| Parameter | Choices |
| --- | --- |
| format | plain text, Markdown, YAML, JSON, XML tags, tables |
| content | signals, claims, or both; citations inline or by id |
| granularity | each signal, a summary per stream, deltas against a snapshot |
| order | by time, by object, by priority |
| time | absolute or relative; where timestamps sit |
| budget | how much fits before older content is summarized |

**Cache layout (default):** stable first, changing last, and nothing already sent rewritten: instructions and
the environment's schema (streams, objects, actuators), then a snapshot of the objects that matters, then the
events appended in order. Timestamps, tool sets and instructions that change mid-session break the cached prefix
([prefix-stability study](https://neurips.cc/virtual/2026/162685) finds a badly arranged loop can cost more than
no caching). The gateway already meters `tokens_cached` (S-106), so a view's cache rate is a KPI on its card.

**Under pass-through** the view is two things Substrate controls: the format of the events a channel pushes,
and what Workbench's MCP tools return. Claude Code manages the rest of the context (compaction, its own cache
layout), and that stays its job. A self-lever lets the LLM ask for a different view (a summary instead of raw
signals), as a `propose`.

## Environments nest (decided as a shape; built later)

A child environment is an object in its parent's environment:

- its **streams** are its escalations, KPIs, verdicts and activity, under its own routing keys, so the parent
  subscribes with `<child>.#`;
- its **actuators** are what the parent may do to it: start or stop it, change its configuration, approve or
  retire its components, take over an event;
- its **gates** work as anywhere else: the parent changing a child's structure is `propose` until trusted.

Escalation goes up a level at a time; only the top reaches a person. The **top level is the system itself**: the
map (objects: components, services, packages), the observer (streams: what runs) and interviews (intent). That is
where the map work done so far belongs. A child's whole configuration is a component with a card from the
parent's side, judged like any rule.

**The one rule built in from the start:** an environment's interface (streams, objects, actuators, gates) is
exactly what a parent sees of it as an object, so nesting needs no redesign.

## The chimera: the root and its goals (decided, S-130)

The root environment is the **chimera**: one system that finds components, or makes and changes them, as its
goals require. Every other environment is a child of it. Its goals, in the order they bind:

1. **Values and constraints** (floor, changed only by the owner): the gates, the privacy rules for personal
   streams (`docs/privacy.md`), the budgets, and what the judge holds. Nothing optimizes against these.
2. **The owner's preferences** (from what they say, in interviews and in the review lane, as their own claims).
3. **Self-optimization** (seed): lower cost and fewer LLM calls per event, fewer escalations to the owner, at
   equal or better quality, every change judged against what it replaces.

**Budgets** are a floor the owner sets (spend per day, per caller, per model) and signals the chimera reads (the
gateway's meter). Choosing a model or a compute placement within the budget is a self-lever; raising a budget
is always the owner's.

**The children, in order:** the companion (a persistent voice and avatar assistant working in the background),
then embodied environments it acts in: VRChat or Virt-A-Mate for presence as a 'hologram', ROS2 for a robot in
simulation and later in operation. Each is nested by the interface rule, so the companion acts in them through
their actuators under the same gates and budget. A personal stream (the owner's voice, messages, files) carries
the privacy floor from its first signal.

### Privacy: adjustable, with defaults that flag and prevent exfiltration (decided, S-131)

The rules in `docs/privacy.md` are the defaults, and they hold until the owner loosens one for a named stream
(a review-lane decision: who, when, why). The default is to **flag and prevent**: personal content does not go
to a hosted model, and an attempt is refused and flagged rather than silently allowed. The gateway is the one
place that can enforce this, so every model call goes through it, **Claude Code's included**
(`ANTHROPIC_BASE_URL` at the gateway), and each caller's key names the providers it may reach. Loosening P3 or
P4 for the companion's text is then one change to one key, visible in the record.

### Placement is a trade-off the system can choose (decided, S-131)

On the owner's machine today (a GTX 1070, 8 GB, weights already partly offloaded to system RAM), each part runs
on the GPU or the CPU, at a cost in latency: Gemma 4 26B or 12B for the local model, speech parts on the CPU.
These are parameters on each component's card (placement, model, quantization), measured for latency, quality
and memory, and choosing among them within the budget is a self-lever; the owner can pin any of them.

### The browser client is an environment (decided as a shape, S-131)

Workbench's browser client is where the owner is, so it is an environment of its own, a child of the companion:

- **Sensors** from browser APIs: microphone, camera, text, and others as needed (screen, location), each off
  until the owner turns it on, each a personal stream under the privacy floor.
- **Actuators:** the speaker, the avatar's rendering, the page itself (messages, notifications, the review lane).
- **Transport:** today the shell gets Server-Sent Events of changed ids (`NOTIFY` on `wb_events`) and sends by
  HTTP. Media needs a two-way binary path (a WebSocket, or WebRTC if latency demands it) on Workbench's server.
- **Rate:** raw audio and video do not go through pgmq frame by frame (Postgres's rate ceiling). The browser's
  media goes straight to its pipeline; what the pipeline makes (an utterance, a transcript, a detection) is the
  signal published to the topics, and raw media is kept, if at all, as files under the retention rule (P7).

### Perception pipelines trade interpretability against refresh rate

Every pipeline sits somewhere between fast and shallow and slow and rich, and can run both at once:

| | Fast path | Slow path |
| --- | --- | --- |
| Hearing | voice activity, wake word, speaker turn | speech-to-text, then what was meant (claims) |
| Sight | motion, presence, face or hand landmarks, many times a second | a vision model's description or answer, a frame every few seconds or on demand |

The fast path's signals decide when to spend on the slow one (someone spoke; something moved), and the LLM can
ask for the slow path directly. The rates, models and the switching rule are card parameters, so the balance is
measured per machine and per task rather than fixed. Speech candidates named by the owner: **Kokoro** (a Rust
implementation) for text-to-speech and **NVIDIA Parakeet TDT** for speech-to-text; versions, licences and
CPU latency are checked with the `research` skill before they are pinned (rules 1, 3, 6).

## Assumptions, as parameters

Each layer is switched on per environment and has to beat pass-through on the same work, on quality, cost or how
much reaches a person. A layer that does not stays off.

| Layer | Its assumption |
| --- | --- |
| Raw readings into claims | encoding helps more than it loses |
| Reactive handlers, in parallel | cheap pattern matching takes load off the LLM without missing things |
| Escalation filtering | the LLM judges better with less in its context, and can query the rest |
| The view's format and layout | a given rendering suits a given model; differs per model and arrangement |
| Serial arbitration per actuator | needed once there is more than one actor |
| Self-levers (subscribe, mute, add or retire a handler, set a threshold) | the LLM tunes its own setup well; structure changes are `propose` |
| Nesting | splitting off a child lowers cost or escalations without losing quality |

## Prior art

From one round of searches (2026-11-17), mostly abstracts; CogRec, Graphiti's code and Global Workspace Agents
were then read in full (S-129).

| Part | Closest work |
| --- | --- |
| Shared space, broadcast | blackboard systems with LLMs, the ones with results: [LbMAS](https://arxiv.org/html/2507.01701v1), [Google's data-discovery blackboard](https://arxiv.org/abs/2510.01285v2). [Global Workspace Agents](https://arxiv.org/html/2604.08206) (2026), read in full: a design with no evaluation at all, and a serial four-phase loop with fixed roles, not parallel subscribers; ideas only (an explicit "respond or think more" tag from an arbiter; compressing short-term memory into a retrievable long-term store past a threshold) |
| Distilling LLM decisions into rules | [CogRec](https://arxiv.org/abs/2512.24113) (Soar chunking of LLM answers; results, but rules never tested or removed); [NL2GenSym](https://arxiv.org/pdf/2510.09355v1); [LATM](https://arxiv.org/abs/2305.17126v2) |
| Claims with provenance, over time | [Graphiti](https://github.com/getzep/graphiti) (episodes, bi-temporal facts; no interpreter, confidence or review; times overwritten in place) |
| Rules written by an LLM, run without it | [llm-trigger](https://github.com/c4pt0r/llm-trigger); [LLM4CEP](https://pure.uva.nl/ws/files/201121899/24-LLM4CEP.pdf); [reactive synthesis](https://arxiv.org/html/2402.16905v1). All start from a person's request, not from the observed stream |
| Cheap first, escalate | [FrugalGPT](https://www.emergentmind.com/papers/2305.05176); [routing and cascades review](https://web.stanford.edu/~shuhuiq/blog/review-routing-cascades.html) (no router clearly beat the trivial one on RouterBench) |
| Event logs, actors | [OpenHands events](https://docs.openhands.dev/sdk/arch/events); [AutoGen Core](https://www.mintlify.com/microsoft/autogen/core/overview); [ambient agents](https://snowplow.io/blog/what-are-ambient-agents) |
| Environment interface | [OpenEnv](https://huggingface.co/docs/openenv/tutorials/mcp-environment) (reset/step/state with MCP tools, for training) |
| Self-change | [Letta](https://medium.com/@piyush.jhamb4u/stateful-ai-agents-a-deep-dive-into-letta-memgpt-memory-models-a2ffc01a7ea1); [Gödel Agent](https://arxiv.org/html/2410.04444v2); [Darwin Gödel Machine](https://arxiv.org/pdf/2505.22954) (archive of versions, empirical checks) |
| Frame | [CoALA](https://huggingface.co/papers/2309.02427); [cognitive architectures to language agents](https://arxiv.org/pdf/2607.23942) |
| Nesting (not yet searched) | Erlang/OTP supervision trees, Kubernetes controllers, holonic multi-agent systems, hierarchical RL |

What appears new is the combination: pass-through as the baseline every layer must beat; components distilled
from the observed stream rather than from a request; reviewed claims rather than derived edges; and a real
harness rather than a research loop over a bare model API.

## Open

- What the LLM sees by default: everything, or what components escalate plus queries (recommended: the latter,
  once there are components; everything under pass-through).
- The judge's runner: a script, or one of Inspect AI, promptfoo, DeepEval.
- The default view's format, until one has been measured on the first environment's model.
- Whether channels work with Claude Code on a non-Anthropic model through the gateway; the first thing to test.
- The first system to put an environment on.
