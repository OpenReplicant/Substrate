# Plan

The one current plan (S-124, 2026-11-17). It replaces the plans in `docs/archive/` (the spec and its build plan,
the experiment-first direction, the handoff, the task briefs); those are kept as history and are not to be worked
from. Every default and its reason is still in `DECISIONS.md`.

## What Substrate is now

An agent framework. You put an environment on a system you need, run it, and watch and change it in Workbench,
which is Substrate's web UI and store (rebuilt on the fresh tree, S-137). Its shape is `docs/framework.md` (S-125): the environment is data in
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
| 3a | **The fresh tree** (S-137): delete what is not carried over in one commit; `setup` and `check.sh` pass on what remains | the stack (db, gateway, caddy, tools) up from the fresh tree; `scripts/check.sh` passes |
| 3b | **The store** (S-135): entity, statement, reference, span, revision; typed values; ranks and the usable value; constraints on properties, reported; a page per entity; hash-pinned spans that flag what cites them; the agent's `search`, `read`, `expand`, `locate` over MCP; Ontop in Wikidata's two RDF shapes, pgGraph, pgvector; v1's people's statements, open decisions and interview answers imported | tests in a throwaway database pass; a changed span flags its statements and what was derived from them, with no model call; v1's imported statements are readable as pages |
| 3c | **The real-time environment:** pgmq topics for streams (`<env>.<stream>.<kind>`), a queue per actuator, gates (`free`, `propose`, `deny`), proposals as decisions, escalation as a topic; the channel server (stdio MCP, `claude/channel`, archived only on `ack`) | a published signal reaches a subscribed channel, an unacknowledged one comes back, an actuator call behind `propose` waits for a person |
| 4 | **The companion, text first, pass-through.** In its own container (S-136), on Haiku with the owner's login through the gateway. Its streams: the owner's messages, the gateway's meter (spend per caller), a clock. Its actuators: reply, start a background task, propose a budget or model change. A Claude Code session kept open, fed by the channel. The privacy defaults (`docs/privacy.md`) apply, P3 and P4 loosened for its text stream only (S-136). A small page to talk to it. First test inside it: does a channel work with Claude Code through the gateway (subscription mode) | the owner talks to it in text and it does background work end to end; every signal, call and action is in the record; budget changes are proposals the owner decides |
| 5 | **The browser client as an environment, and the voice head.** A two-way media path on Workbench's server; the browser's microphone and speaker as sensor and actuator. The voice head as a pipeline component: voice activity, speech-to-text (Parakeet TDT), a fast local model for turn-taking and short answers, text-to-speech (Kokoro, Rust); versions and placement (GPU or CPU on the 1070) checked with the `research` skill and measured. It answers what it can and hands real work to the Claude Code session, which reports back through it | a spoken conversation with latency the owner accepts; LLM calls per event and cost per hour on its card |
| 6 | One distilled component with its card, and the judge interface's first filler (a script as the judge user, a held-out slice of the record, whole days held out) | a verdict on the component against pass-through; promoted or refused on it |
| 7 | Sight: the camera as a sensor, a fast path (motion, presence, landmarks) and a slow path (a vision model on demand) as components | the companion notices and answers about what it sees, with refresh rate and cost per hour on the cards |
| 8 | **The avatar, then mixed reality on the Quest 3.** The talking head first (three.js, `@pixiv/three-vrm`, mouth by expression presets); then the browser environment in an `immersive-ar` WebXR session: planes, meshes, anchors, depth, head and hand pose as sensors; the avatar placed in the room (`move_to`, `place_on`, `look_at`). First test on the device: does `getUserMedia` give the passthrough camera (if not, a native Quest app as another adapter) | the avatar talks, stays where it was put in the room and looks at the owner; recognition components on their cards (where they run, how often, cost) |
| 9 | The next embodied child: Resonite (in-world editing; ResoniteLink's WebSocket and community MCP servers, every world-changing tool gated), VRChat, Virt-A-Mate or a ROS2 simulation (the owner's pick), by the same adapter pattern | the companion acts there through the same avatar actuators, under the same gates and budget |

Self-levers beyond budget and model choice, and the other layers in `docs/framework.md`, come as these steps
need them, each tested against pass-through. Workbench is no longer frozen: add what these steps need, and
nothing they don't.

## Deferred

Morphogen R&D (statistics, the judge's own gateway and meter, the queue, GitHub Actions, the evidence log), the
case-and-scorer kit and the environment contract's generalisation, held-out cases by script, the paper catalog's
publication and reproductions, the hosted mapper and hosted judging, the slot model
(`docs/archive/slots.md`).

## The owner's to decide

- Which embodied environment comes after mixed reality (step 9).
- Rotating the Postgres password; putting the Gemma model at the gateway.
- The licence and whether the repository goes public.
