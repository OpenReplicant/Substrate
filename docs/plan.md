# Plan

The one current plan (S-124, 2026-11-17). It replaces the plans in `docs/archive/` (the spec and its build plan,
the experiment-first direction, the handoff, the task briefs); those are kept as history and are not to be worked
from. Every default and its reason is still in `DECISIONS.md`.

## What Substrate is now

An agent framework. You put an environment on a system you need, run it, and watch and change it in Workbench,
which is Substrate's web UI and store. Its shape is `docs/framework.md` (S-125): the environment is data in
Postgres, pass-through to Claude Code is the default, components distilled from the record carry cards, a judge
tests them on cases their author never saw, and environments nest. Morphogen stays a part you can use as it is;
no more work goes into it for now.

## What already exists

- **Packages** (`packages/`): an environment (what the agent senses and may do, and how its outcome is
  measured) and the agent configured for it, started by naming it in `PACKAGES`. `lookups` and `papers` are the
  two so far.
- **The model gateway** (Bifrost): every model call goes through it with its caller's key and is recorded.
- **Workbench** (`workbench/`): typed items with claims beside every value, a web shell, an API, extractors, live
  events, and an MCP server for Claude Code.
- **The map, the observer and interviews** (`plugins/substrate/`, the `interview` skill): what a system is,
  what runs, and what the people who own it say about it.

## Steps

| # | Step | Done when |
| --- | --- | --- |
| 1 | Get the stack up on the machine you work on (`setup` skill) | `scripts/check.sh` passes |
| 2 | Read the three closest works in full (Global Workspace Agents, CogRec, Graphiti's data model) and the current Claude Code channels docs; amend `docs/framework.md` where they change it | the page cites what was read and what changed (done 2026-11-17, S-129; checking the claim fields against Workbench's schema waits for step 1) |
| 3 | The owner picks the first system | done (S-130): the companion, a persistent voice and avatar assistant that works in the background and manages its own model and compute budget, the first child of the chimera (the root environment) |
| 4 | **The companion, text first, pass-through.** Its streams into pgmq topics: the owner's messages, the gateway's meter (spend per caller), a clock. Its actuators: reply, start a background task, propose a budget or model change. A Claude Code session kept open, its model calls through the gateway, fed by our channel (a pgmq queue behind `notifications/claude/channel`, archived only on `ack`). The privacy defaults (`docs/privacy.md`) apply from the first message: content is flagged and kept from hosted models until the owner loosens a stream. First test inside it: does a channel work with Claude Code on the gateway's local model | the owner talks to it in text and it does background work end to end; every signal, call and action is in the record; budget changes are proposals the owner decides in Workbench |
| 5 | **The browser client as an environment, and the voice head.** A two-way media path on Workbench's server; the browser's microphone and speaker as sensor and actuator. The voice head as a pipeline component: voice activity, speech-to-text (Parakeet TDT), a fast local model for turn-taking and short answers, text-to-speech (Kokoro, Rust); versions and placement (GPU or CPU on the 1070) checked with the `research` skill and measured. It answers what it can and hands real work to the Claude Code session, which reports back through it | a spoken conversation with latency the owner accepts; LLM calls per event and cost per hour on its card |
| 6 | One distilled component with its card, and the judge interface's first filler (a script as the judge user, a held-out slice of the record, whole days held out) | a verdict on the component against pass-through; promoted or refused on it |
| 7 | Sight: the camera as a sensor, a fast path (motion, presence, landmarks) and a slow path (a vision model on demand) as components | the companion notices and answers about what it sees, with refresh rate and cost per hour on the cards |
| 8 | The avatar, then the first embodied child environment (VRChat, Virt-A-Mate or a ROS2 simulation, the owner's pick), nested under the chimera by the interface rule | the companion acts there through that environment's actuators, under the same gates and budget |

Self-levers beyond budget and model choice, and the other layers in `docs/framework.md`, come as these steps
need them, each tested against pass-through. Workbench is no longer frozen: add what these steps need, and
nothing they don't.

## Deferred

Morphogen R&D (statistics, the judge's own gateway and meter, the queue, GitHub Actions, the evidence log), the
case-and-scorer kit and the environment contract's generalisation, held-out cases by script, the paper catalog's
publication and reproductions, the hosted mapper and hosted judging, the slot model
(`docs/archive/slots.md`).

## The owner's to decide

- Whether to loosen P3/P4 for the companion's text stream (the default flags and refuses it; S-131), or to run its Claude Code on a local model.
- Which embodied environment comes first (step 8).
- Rotating the Postgres password; putting the Gemma model at the gateway.
- The licence and whether the repository goes public.
