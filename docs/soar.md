# MetaSoar: Soar, with Substrate on its impasses

The spec for Substrate's first target, the repository `OpenReplicant/MetaSoar` (S-160, S-161, 2026-11-18; supersedes S-154's design, which is kept below as
hypotheses). **The original Soar, unchanged, with one hook: an impasse its own knowledge cannot get out of goes
to Substrate, which proposes a change, judged by Morphogen and let in by the gate.** Nothing else is ours. What
Substrate adds over time, and whether it rediscovers anything we would have built in, is the result.

Owner, 2026-11-18: "it might be good to implement something as close to original as possible, if it can just
reach out to Substrate on any impasse and see what changes that way", and "our opinions should be removed but
where there is value, leave them in a section on experimental hypothesis that could be trialed later... maybe
they'll make it into catalogs of options substrate uses to modify the base."

## The litmus test: learning to play games

Owner: "maybe just combining base Soar + Substrate we'll be able to interface with arbitrary games (embodied
environment sim w/feedback) and have the framework to learn how to play. (somehow i think that's the litmus
test)". So the test is: **given a game it has never seen, through one generic adapter, does Soar with the hook
get better at it over episodes, and does what it learned make the next game faster to learn?**

## The base

- **Soar 9.6.5** (`releases/9.6.5`, 2026-05-06; BSD, its `LICENSE.md`, read 2026-11-18), built from source in
  its own container, driven through its own interface (SML), with its own memories (semantic and episodic in its
  SQLite, as the manual describes, ch. 6 and 7). Chunking and reinforcement learning are Soar's own, on or off as
  Soar's settings allow.
- **The agent starts with the least that lets it act**: the rules that read the adapter's input and write its
  actions, and nothing about any game.

## The only things we add

1. **An environment adapter**: an environment's observation onto Soar's input link, Soar's output-link commands
   onto the environment's actions, its reward onto Soar's reward link (ch. 5). Written once against a standard
   environment interface (which one, picked with the `research` skill; Gymnasium's observation, action and reward
   is the lead, with arbitrary observation and action spaces, text among them), not per environment. This is
   what "environment" means here: any senses and any actions, with feedback; a game is one kind. It is the
   judge's, not the agent's: Substrate may not change it.
2. **The impasse hook**, a watcher outside the agent, on the judge's side with the adapter: it sees the kernel's
   decisions and impasses through SML, so the agent's own rules (which Substrate changes) cannot suppress it and
   the agent cannot learn to hide being stuck. Soar reaches impasses constantly as normal problem solving, so the
   hook fires only on one its own knowledge cannot leave: no progress for N decision cycles, the goal-depth limit reached, or the same
   impasse recurring across episodes. It calls Substrate's `improve` (`docs/seed.md`) with the trace: the impasse,
   the working memory above it, the recent decisions, the episode's reward so far. N and the recurrence count are
   settings, and the hook's only opinions.
3. **Learning between episodes, not within**: `improve` takes minutes to hours, so a stuck episode ends (stalls,
   times out or gives up), and Substrate's change, once let in, applies from the next one: new rules loaded into
   the kernel, or a new build.

## What Substrate may change, as Morphogen cells

| Cell | `change` | Stays Soar? |
| --- | --- | --- |
| rules | the agent's productions (`agent/**`) | yes: the reference check holds by construction |
| settings | Soar's own parameters (learning on or off, RL's rates, memory settings), bounded | yes |
| architecture | the kernel's source | no: this starts the architecture lineage |

Soar is BSD C++ built from source here, so the architecture can change by three routes, and which one Substrate
takes, and when, is part of the result: **edit the kernel's C++ and rebuild** (a new decision procedure, memory
or kind of substate); **replace a part behind SML** (a module reimplemented elsewhere, on Postgres for instance,
with the adapter and the rules still working); or **leave the kernel alone** and work through rules and settings,
which keeps it Soar.

Fixed, the judge's: the adapter, the games, the measures, the hook's thresholds, the gate policy.

## Measured

Per game: return per episode over episodes (the learning curve), episodes to a level of play, Substrate's model
calls and cost per accepted change, changes proposed and let in. Across games: **generalisation**, on games held
out by kind (none of the agents was built or tuned on them): how fast a new game is learned with what earlier
games left, against starting fresh.

Compared with: **vanilla Soar** (the base, no hook, its own chunking and RL only); **a vanilla LLM agent** (a model
in a harness, playing directly); **Soar with the hook**. The expectation: vanilla Soar learns only what its RL can
reach from the starting rules; the LLM agent plays passably at a high, flat cost per move; Soar with the hook
starts badly and improves, its cost per move near zero, its cost per change falling. Where it stops improving is
where the base's scope ends (owner: "i think what we'll find is that Soar's scope is more narrow than what is
needed for higher-generalization"), and whether Substrate then reaches for the architecture cell is the next
result.

## Environments

To be picked with the `research` skill, symbolic first, since Soar needs symbols on its input link:
- Soar's own puzzles from its tutorials: water jug, blocks world. Eaters and TankSoar are not packaged with 9.6.5
  ("we are not packaging eaters or tanksoar this release", the release's notes); an older release or a
  reimplementation behind the adapter, if wanted.
- Grid and text games with a standard interface and feedback (leads: BabyAI, MiniHack, Crafter, TextWorld, and the
  games BALROG benchmarks agents on).
- Later, games seen only as pixels: perception is then something Substrate has to build or choose, which is itself
  a test.
- **Conversation**, as one environment among the others, not the agent's nature: the observation is what was said
  and its timing (speaking or silent, for how long), the actions say, wait and stop, the reward from the exchange
  (answered, talked over, corrected). Soar has no language of its own (its history with language is hand-built
  rules: NL-Soar's parsing, Rosie's restricted English, both to be read before citing), so whether Substrate
  reaches for an LLM for language, or grows rules that model language without one, is the finding. Until then the
  companion (an LLM) stays the owner's way to talk *about* the agent, reading its trace.
- **A Linux terminal**: the observation is the screen and the command's output, the actions are keystrokes or
  commands, the reward a task done (a file found, a test passing). Much of it may simply defer to an LLM; whatever
  repeats (the same commands for the same kind of task) is what rules can learn.

## Lineages

0. **The base with the hook**, rules and settings only: stays Soar.
1. **Architecture changes** let in: no longer Soar; how far it drifts from lineage 0, and what it gains, are part
   of the result.

## First steps

1. Soar 9.6.5 in a container; a Soar agent driven through SML; Eaters played, its trace written out.
2. The adapter, against the picked environment interface; one grid game played by the starting rules.
3. The hook: an unresolved impasse reaches Substrate's `improve` with its trace; a change comes back as a pull
   request on the agent's rules, judged and gated.
4. The curve on that game; then a held-out game.

## Experimental hypotheses, to trial later

Our earlier design (S-154, S-159), kept for its value, not built in. Each becomes a candidate in a catalog Substrate
may draw on when it changes the base; whether Substrate reaches for one unprompted is itself a finding.

- **Soar rebuilt on Postgres.** Working memory as tables, rules as SQL matched on change, preferences and the
  decision cycle as functions, pgmq for the cycle, pgvector and graphs for retrieval. Why it might pay: memory
  shared with other agents and tools, queries across runs, scale. Checked, if built, against the kernel by
  comparing traces cycle by cycle.
- **An LLM resolving impasses inside a substate**, in seconds rather than between episodes: the superstate's
  working memory serialised for it, an operator or preferences back. The hook already has an LLM in the loop
  (Substrate's), but slowly and between episodes; this would put one inside the cycle.
- **Chunking from an opaque reasoner**: an LLM's reasoning cannot be backtraced, so a chunk is written from the
  impasse and its result and proven on held-out impasses before use. Morphogen judges commits, so until a run-time
  judge exists such chunks would be judged in batches.
- **Beliefs with evidence**: semantic memory whose facts carry their sources and the spans they rest on, flagged
  when a source changes, retracting what was inferred from them.
- **Gated acts**: output-link commands to the real world through actuators with `free`, `propose`, `deny` gates.
- **Two grains of rule**: productions, and cards (a prompt and settings for a model) called by an operator.
- **Reflexes and bodies**: loops faster than a decision cycle kept outside it (motor control, voice activity,
  playback), feeding the input link. **The voice head as a body** (S-159): turn-taking as Soar decisions (take the
  turn, wait, answer, hand over, back-channel, stop), the wording from a model, reward from being talked over,
  long silences and handoffs, all already in its record. It needs answers within a breath, so it waits until
  rules exist or an in-cycle LLM (above) is let in.
- **Model calls per decision falling** as chunks replace impasses, when an LLM is in the cycle: the curve S-154
  predicted.
- **Language without an LLM**: rules (and Soar's memories) that model language well enough to converse, grown
  from the conversation environment by Substrate's changes alone; the strongest form of the narrow-scope question.
- **ACT-R's mechanisms** (from memory, to be read before use): activation-based declarative memory (retrieval time
  and failure from use, decay and noise), utility learning with noise, perceptual and motor modules with human
  timing. Later, ACT-R as a second base behind the same adapter (a hook on failed retrievals), and as a **model of
  the person** the agent acts with, fitted to their own record (the voice head's timings and requests): theory of
  mind, a later use, not the agent's base.

## Read for it

The Soar manual, chapters 2 to 7 (https://soar.eecs.umich.edu/soar_manual/, read 2026-11-18): working memory as
"a tuple consisting of three symbols: an identifier, an attribute, and a value" (ch. 3); impasses tie, conflict,
constraint failure, no change (ch. 3); chunking "disabled by default" and with correctness filters not yet complete
(ch. 4); RL as numeric-indifferent preferences, Sarsa or Q-learning, reward on the reward link (ch. 5); semantic and
episodic memory in SQLite (ch. 6, 7). Chapter 2's decision cycle, I/O and o-support sections are still to be read
whole, before the adapter is written.
