# Soar on Postgres, with LLM reasoning and beliefs with evidence

A design note (S-154, 2026-11-18). Substrate becomes a cognitive architecture: **Soar, rebuilt on Postgres, with
an LLM resolving its impasses and a semantic memory of beliefs that carry their evidence.** A neuro-symbolic
hybrid agent: the symbolic part decides fast and is inspectable; the neural part is called only where the
symbolic part has no answer; what it works out is compiled back into rules, which are tested before they are
trusted. Owner, 2026-11-18: "no one needs another LLM harness, but a Soar implementation on our stack would be
something worth writing about, with whatever wraps an LLM for practicality."

## The choice (option C)

| | What | Why not, or why |
| --- | --- | --- |
| A | Soar's own kernel (C++, its Python bindings), Postgres as its environment, an LLM as an operator | quick and faithful, but Postgres is only the world it lives in, and "Soar plus an LLM" is already being done |
| B | Soar's architecture rebuilt on Postgres | the version worth writing about, but without a check it drifts into "Soar-inspired" |
| **C** | **B, checked against A**: the real kernel runs beside it as the reference, on the same agents and tasks | **chosen**: "we implemented Soar" becomes something shown, and every place we depart from Soar is named and argued |

The reference: Soar 9.6.5 (`releases/9.6.5`, 2026-05-06; BSD, its `LICENSE.md`, read 2026-11-18), built from
source in its own container, never linked into Substrate's code.

## Soar's mechanisms, and their form here

From the Soar manual (https://soar.eecs.umich.edu/soar_manual/, chapters 2 to 7, read 2026-11-18). Rows marked
*to confirm* rest on parts of chapter 2 not yet read whole (the decision cycle's phases, I/O, o-support).

| Soar (manual) | Here | Exists today |
| --- | --- | --- |
| **Working memory**: "a tuple consisting of three symbols: an identifier, an attribute, and a value", "a graph rooted in the states" (ch. 3) | a table of `(id, attr, value)` rows per agent, with the state graph as foreign keys; each WME timetagged (the row's id) | no; signals (`env.signal`) are what arrives on the input link |
| **Input and output links** (*to confirm*) | the input link is written from signals (each environment's streams); the output link is read into actuator queues | yes: signals, and actuator queues behind gates (`env`, S-143) |
| **Productions**: "Operators are proposed by rules that test features of the current state" (ch. 2) | rules as SQL matched against working memory, incrementally on change (a Rete or TREAT-like match over the WME table: the first thing to measure) | no |
| **i-support and o-support**: elaborations are "automatically retracted when the situation changes"; applications make "persistent changes" (ch. 2) | i-supported rows carry the instantiation that made them and go when it unmatches; o-supported rows stay | no |
| **Preferences and the decision**: "a fixed procedure that interprets preferences" (ch. 2); acceptable, reject, better, worse, best, worst, indifferent, numeric (ch. 3) | a preference table per decision; the decision procedure as one SQL function, run once per cycle | no |
| **The decision cycle** (*to confirm*: input, proposal, decision, application, output) | one cycle per tick, over pgmq: input from signals, proposal and elaboration to quiescence, decision, application, output to actuators | the loop exists as pass-through, not as a cycle |
| **Impasses**: tie, conflict, constraint failure, no change (ch. 3); "the goal in the substate is to resolve the impasse" (ch. 2) | a substate row; **its problem solving may be an LLM** (below) | pass-through is a crude impasse: nothing handles the signal, so the LLM gets it |
| **Chunking**: "Soar's experience-based mechanism for learning new procedural knowledge", built by backtracing "through the instantiation graph" (ch. 4) | two kinds (below): Soar's own, for symbolic substates; **compiled from the LLM's result and proven by the judge**, for neural ones | the author and the judge (S-151), for one coarse component |
| **Reinforcement learning**: Q-values as numeric-indifferent preferences of RL rules; Sarsa or Q-learning; reward on the reward link (ch. 5) | numeric preferences on rules, updated from rewards; rewards from the owner's decisions, overrides and the judge's measures | no |
| **Semantic memory**: SQLite; stored deliberately; cue-based retrieval "whose augmentations exactly match an agent-supplied cue", ties by activation (ch. 6) | **the store**: statements with ranks, references and pinned spans; retrieval by cue over statements, activation as a column | yes, the store (S-135, S-138) |
| **Episodic memory**: SQLite; recorded automatically, "the entire top-state of working memory"; retrieval as "a nearest-neighbor search" (ch. 7) | the record: working memory snapshots per output (or per cycle) beside `env.signal` and `env.action` | partly: the record of signals and actions |

The hierarchy of contexts the owner described (a primary agent starting sub-projects with their own context) is
Soar's substate stack: a sub-project is a substate with its own working memory and goal, and its results return
to the state above. Environments nesting (`docs/framework.md`) becomes that, not a separate mechanism.

## Where we depart from Soar, on purpose

Each is a claim the write-up has to support with measurements.

1. **An LLM resolves impasses.** When no rule proposes an operator, or several tie, the substate's problem
   solving may be an LLM call: it sees the superstate's working memory (serialised, the view, S-134) and
   answers with an operator, preferences, or new WMEs as results. Whatever wraps the call (a plain chat request,
   Claude Code, OpenCode) is plumbing inside the substate, chosen by measurement, not the architecture.
2. **Chunking from an opaque reasoner.** Soar's chunking backtraces through the rules that fired in the
   substate; an LLM's reasoning cannot be backtraced. So the chunk is written, not derived: from the impasse,
   the superstate it saw and the result it returned, an author proposes a rule (conditions on the superstate,
   the result as its action), and the judge tests it on held-out impasses of the same kind before it is used.
   The manual itself lists correctness gaps in chunking ("correctness filters have not yet been implemented for
   all the identified potential sources", ch. 4); here every learned rule is tested, which is the part that is
   new.
3. **Two grains of rule.** A production in SQL (symbolic, matched every cycle) and a card (a prompt and settings
   for a model, S-151: neural, called by an operator). A chunk can be either; the cheaper one that passes wins.
4. **Beliefs carry evidence.** Semantic memory is the store: a retrieved fact comes with its references and the
   exact spans it rests on; a changed source flags what cites it (S-138), and a flagged belief retracts what was
   elaborated from it. Soar's semantic memory has no notion of where a fact came from.
5. **Acts are gated.** Output-link commands to the world go through actuators with gates (`free`, `propose`,
   `deny`); a proposal waits for a person (S-143). Soar has no such boundary.
6. **Reflexes outside the cycle.** Loops faster than a decision cycle can run (the voice head hearing and
   speaking, S-149) stay outside it, and feed the input link with what they did.

## The first body: the voice head (S-159)

The voice head (S-149, S-153 in Substrate's tree) is the first body the hybrid lives in, and the interface to
build real-time embodiment on: every later body (the VRM avatar, a game, a robot) has the same three parts. The
code may or may not be reused; the shape is what carries over.

| Layer | In the voice head | Rate | In a later body |
| --- | --- | --- | --- |
| **Reflexes**, outside the cycle | microphone frames, voice activity (Silero), speech to text (Parakeet), text to speech (Kokoro), playback, the mouth following loudness, stopping playback the instant the owner speaks | every 20 ms frame | motor control, physics, lip sync, a game's input timing |
| **Soar**, System 1 decisions | turn-taking and what kind of reply: take the turn, wait, answer, ask again, hand over, back-channel ("mm"), stop | per decision cycle, a decision well inside a breath (budget to be measured) | where to look, when to move, which skill to use |
| **An LLM in an impasse substate**, System 2 | the wording of a reply, when no rule has one; whether a request is real work, when rules cannot tell | seconds, streamed | a plan, an explanation, a new situation |

**The input link** (what the reflexes write, as working memory elements): the owner speaking or silent, and for
how long; a partial and a final transcript; the head's own state (speaking, the sentence it is on, how much is
left); an interruption (the owner spoke over it, and after how much); the companion's answers arriving; the
clock. **The output link** (commands the reflexes carry out): `say` (text, or a request for wording), `stop`,
`wait`, `backchannel`, `handoff` (a request to the companion), `expression` (the face). Speaking is a command
the reflexes carry out sentence by sentence, so Soar can stop it between cycles without waiting on speech.

**Reward**, for reinforcement learning on the turn-taking rules: being talked over soon after starting
(negative), a long silence after the owner finishes (negative), a handoff the companion completes (positive), a
handoff it refuses as small talk (negative), the owner's explicit approval or correction (strongest). All of
these are already in the voice head's record (`companion.voice.heard`, `companion.voice.said`: timings,
interruptions, handoffs), so the first rules can be compared against the current voice head's behaviour on
recorded conversations before any live one.

**Chunking here:** when the LLM substate answers the same kind of utterance the same way (greetings, "what time
is it", "hand that over"), the answer becomes a rule that replies with no model call; that is where the curve
(model calls per utterance falling) should show first. **Measured:** time from the end of the owner's speech to
the first word, interruptions per minute, handoff agreement on the judge's labelled cases (S-151's 30), and
model calls per utterance, against the current voice head as the baseline.

## Checked against the reference

The same agents run on Soar 9.6.5 and on this implementation, and must make the same decisions:
- the classic tasks shipped with Soar's tutorials and its unit tests (water jug first; which ones the repository
  carries is to be read from it, not assumed)
- a trace per run: each cycle's working memory changes, preferences, selected operator and impasses, compared
  cycle by cycle (where Soar's own choice is random, the seed or the set of acceptable choices is compared)

## Benchmarks, on both sides

To be picked with the `research` skill; these are leads, not choices.
- **Cognitive-architecture tasks:** Soar's own (water jug, blocks world, Eaters, TankSoar) and whatever the
  literature uses to compare architectures.
- **LLM-agent benchmarks:** text and game environments where agents are compared on success and cost (for
  example ALFWorld, ScienceWorld, TextWorld, or BALROG's games, Crafter and BabyAI among them).
- **What we would add:** beliefs under changing evidence (a source changes; does the agent stop acting on what
  it said?).

Measured on each: success; model calls, tokens and cost per decision; latency; and **the curve**: model calls per
decision falling over the run as chunks replace impasses, with success holding. That curve is the result the
architecture predicts.

## Three agents compared, and three lineages (S-157)

Compared on every benchmark: **vanilla Soar** (the 9.6.5 kernel, rules only), **a vanilla LLM agent** (a model in
a harness, no Soar), and **the hybrid**. "Higher generalisation" is measured, not argued: tasks held out by kind
(domains none of the three was built or tuned on); per task, success, model calls and cost; and how much of what
was learned on one domain carries to the next. The expectation: vanilla Soar fails where it has no rules, the LLM
agent succeeds at a high flat cost, the hybrid's cost falls. Where the hybrid stalls is where Soar's scope ends
(owner: "i think what we'll find is that Soar's scope is more narrow than what is needed for higher-generalization").

The hybrid may then change its own architecture: an impasse no rule and no LLM substate resolves becomes a call to
Substrate's `improve` (`docs/seed.md`), judged and gated like any change. Since a changed architecture is no
longer Soar, three lineages are kept: **conformant** (stays Soar, the reference check holds), **the hybrid as
specified** (this note), and **the self-modifying hybrid**, which keeps going. Each is measured against both
vanilla agents; how far the third drifts from the first is part of the result.

## Where it lives

In its own repository, built by Substrate (`docs/seed.md`) and judged by Morphogen. It carries its own spec (this
note, tightened), its `catalog-info.yaml` and `morphogen.yaml`. Its first cell: conformance, scored as trace
agreement with the reference kernel (run as a service image) on agents the builder never sees. From this tree it
takes the store (as semantic memory), the environment's signals and gated actuators (as the input and output
links), and the companion and the voice head (as the first agent that lives in it). The harness question
(S-154's discussion) shrinks to which wrapper an impasse substate uses.

Morphogen judges commits; chunks are learned at run time. Until a run-time judge exists, chunks are written to a
rules file and judged in batches as commits.

## First steps

1. The reference: Soar 9.6.5 built in a container, water jug run, its trace written out.
2. Working memory, preferences and the decision cycle in Postgres; water jug's trace matches.
3. Impasses with an LLM substate; a task with no rules at all, solved by the LLM, every impasse recorded.
4. Chunking from those impasses, judged; the curve on that task.
5. The voice head as the first body (above): its turn-taking as Soar rules with reinforcement learning, replies from an LLM substate, chunked; measured against the current voice head on its record, then live.

## Open

- How rules are written: Soar's own syntax, parsed into SQL (so Soar's agents run unchanged, which conformance
  needs), or a new syntax (not before conformance).
- Incremental matching in Postgres: triggers, a Rete in a process beside it, or both; measured on Soar's
  performance tests.
- What a cycle is in real time: Soar runs as fast as it can; an agent with a voice and a body ticks on signals.
- The write-up: where, when, and with what results.
