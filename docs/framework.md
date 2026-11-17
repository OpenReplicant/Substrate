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
| The source of truth | the claim log: readings kept whole, and claims (subject, property, value, source, time, confidence) beside every value. Append-only; a claim is retracted, never erased |
| Streams in | pgmq topics. A reading is published with `pgmq.send_topic` under a routing key `<env>.<stream>.<kind>` (dot-separated, so a child's keys sit under its parent's); logged queues, archived after handling, so a stream can be replayed |
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
  environment's topics. Channels are a research preview (v2.1.80); read the current docs and pin before relying
  on them (rule 1).
- **Look around:** Workbench's MCP server, to query objects, claims and history.
- **Out:** actions written to actuator queues through MCP, under the gates; hooks and permissions enforce them.

Pass-through is useful on its own, and it is the **baseline every other layer is measured against**.

## Components and their cards (decided)

A component is a handler that subscribes to a pattern and does something: writes claims, proposes an action,
or escalates. Its kind may be a rule, a script, a model call, a Claude Code session, or a person. Components come
from the LLM distilling its own repeated decisions (or from a person), and each carries a **card**:

| Field | Says |
| --- | --- |
| intent | what it is for, in a sentence the owner can check |
| trigger | the pattern it fires on: one event or several aligned in time, over claims |
| action | what it does, through which actuator |
| source cases | the recorded events it was made from, each with what the LLM or person did |
| KPIs | what it must hold to: agreement with what it replaces, cost per event, latency, override rate |
| tests | cases it must handle, and cases where it must not fire |

**Lifecycle:** proposed → judged → active at `propose` → `free` once trusted → demoted when it drifts (overrides
climb in the review lane). Every version is kept, so a component can be rolled back or compared against the LLM
it replaced.

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
- **Morphogen** stays an option behind the same interface, for noisy comparisons (one LLM configuration
  against another, statistics over rounds). No new work on it (S-124).

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

## Assumptions, as parameters

Each layer is switched on per environment and has to beat pass-through on the same work, on quality, cost or how
much reaches a person. A layer that does not stays off.

| Layer | Its assumption |
| --- | --- |
| Raw readings into claims | encoding helps more than it loses |
| Reactive handlers, in parallel | cheap pattern matching takes load off the LLM without missing things |
| Escalation filtering | the LLM judges better with less in its context, and can query the rest |
| Serial arbitration per actuator | needed once there is more than one actor |
| Self-levers (subscribe, mute, add or retire a handler, set a threshold) | the LLM tunes its own setup well; structure changes are `propose` |
| Nesting | splitting off a child lowers cost or escalations without losing quality |

## Prior art

From one round of searches (2026-11-17), mostly abstracts; the first three are to be read in full before building.

| Part | Closest work |
| --- | --- |
| Shared space, broadcast | [Global Workspace Agents](https://arxiv.org/html/2604.08206) (2026); blackboard systems with LLMs: [LbMAS](https://arxiv.org/html/2507.01701v1), [Google's data-discovery blackboard](https://arxiv.org/abs/2510.01285v2) |
| Distilling LLM decisions into rules | [CogRec](https://arxiv.org/pdf/2512.24113v1) (Soar chunking of LLM answers); [NL2GenSym](https://arxiv.org/pdf/2510.09355v1); [LATM](https://arxiv.org/abs/2305.17126v2) |
| Claims with provenance, over time | [Graphiti](https://github.com/getzep/graphiti) (episodes, bi-temporal facts; derived edges are not reviewed claims) |
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
- Morphogen's future: frozen as an option (recommended), slimmed, or folded in.
- The first system to put an environment on.
