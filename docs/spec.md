# Substrate spec: a mind in an organism

What substrate is meant to become. **While this file is in place, Claude Code sessions in this repository build
it out**, one step of the build plan (section 10, tracked in [`build.yaml`](build.yaml)) at a time, with the
`build-out` skill; each step ends with its check passing, and decisions that are the owner's wait for the owner.
Delete this file (or set a step's status to `dropped`) to stop that. The editable copy for discussion is the
Claude Doc "Substrate Spec: A Mind in an Organism"; this file is the one sessions follow, so changes agreed there
are copied here.

## 1. What substrate becomes

Substrate becomes a mind inside an organism, built only from its own stack. Each agent runs the Common Model of
Cognition (CMC); the agents, people and services together form a Viable System Model (VSM) organism. There is
one store (kernel's Postgres), one judge (Morphogen), one gateway (Bifrost), one control plane (compose or
Nomad), one front door (Caddy), one bus (pgmq, in the same Postgres), and every tool runs in a container.

This spec adapts the design "Common Model of Cognition on Claude Code"
(https://claude.ai/artifact/3P6yZSqSBGk8cJHsGH1XpV), which stays as the original design. Every place that
design stood up its own store, server or judge now names the substrate part that does that job, so there is one
way to build each thing.

The design's four principles carry over, with substrate's added:

1. **Working memory is the only hub.** Modules exchange state only through the agent's working-memory scope;
   only a filtered snapshot reaches Claude's context.
2. **Symbols plus numbers.** Every claim and every skill carries numbers (belief, activation, utility, use
   counts) that bias what is recalled and chosen.
3. **Hooks are the architecture; prompts are the content.** Anything that must always happen runs as a hook.
4. **Learning is online and gated.** Utilities and activations update on their own; new or changed skills land
   only with a Morphogen verdict and an owner's approval.
5. **One of each.** One store, one judge, one gateway, one control plane, one bus, one hook set per event. No
   module keeps a private database; the bus is a database in the same Postgres, not a second server.
6. **Nothing on the host but git, python3, the engine and Claude Code.** Every new command runs in
   `substrate-tools` (S-19).

## 2. Module map

Each module of the cognitive design maps to a part substrate already runs or to a kernel module it adds. Nothing
gets its own store: every memory is claims in kernel's Postgres, written by change sets under a role. Work and
notices between parts travel on the bus; facts never do.

| Cognitive module | Substrate part | State today |
| --- | --- | --- |
| Cycle (decide, act, observe) | A Claude Code session, with hooks run through `bin/` in the `substrate-tools` container | Runs |
| Working memory | Kernel's agent working-memory scope (M6-T2), read and written through the kernel MCP memory profile | Planned in kernel |
| Declarative memory | Kernel claims plus recall (BM25 and embeddings, D-60, D-61); a new `activation` module reranks recall | Claims run; activation new |
| Episodic memory | Kernel's `encoder-interaction` turns session transcripts into episode claims; kernel's memory extractor proposes facts from them | Encoder in kernel; substrate wiring new |
| Procedural memory | Claude Code skills (`.claude/skills/`), each with a utility claim | Skills run; utility new |
| Utility and learning | DQV measurement claims written by `encoder-morphogen` from Morphogen verdicts, plus token and cost counts from Bifrost through Prometheus | Planned (S-08, S-05) |
| Skill selection | Claude Code's own skill activation; utility is shown to it, it is not replaced | Runs |
| Perception | Kernel encoders: self, `encoder-backstage`, `observer-prometheus`, `encoder-morphogen`, later `encoder-nomad` | Partly runs |
| Motor | Actuators declared as ontology actions: git branch and PR, Nomad job changes, catalog edits by PR | New |
| Judge and red team | Morphogen | Runs |
| Model calls | Bifrost (Anthropic, OpenRouter, local) | Runs |
| Identity resolution | Kernel M6-T9 resolver, judged by Morphogen (S-07) | Planned |
| Goals and policy | Owner claims in kernel, under the owner role; proposed from the console onto the bus's `owner` queue | Proposal path runs; goal vocabulary new |
| Interrupts and triggers | The bus (pgmq, S-21): `triggers` for what should start a session, `events` for the feed | Queues run; producers and the dispatcher new |
| The owner's view | The console (S-22) behind the front door (S-20), signed in with a kernel login | Runs |

Graph questions (what depends on what) are answered by SQL over claims; a graph extension such as Apache AGE
comes only when an algorithm needs one (kernel D-08), as its own decision.

## 3. Working memory

Working memory is a small, bounded set of claims in the agent's working-memory scope (kernel M6-T2), not a
separate database. It holds what the current session is about:

- the active goal, pointing at the owner claim it serves;
- the entities in focus (at most a dozen), by kernel identifier;
- open conflicts and review items touching those entities;
- the latest Morphogen verdicts on work in progress;
- the skills tried this session and how each went.

**Reading.** At `SessionStart` the hook writes a short summary of the scope into context. Claude Code caps each
injected string at 10,000 characters and replaces anything longer with a 2,000-character preview, so the
summary targets 2,000 characters and links to the rest through recall. At `UserPromptSubmit`, `kernel-mcp-cue`
adds cues for entities the prompt names.

**Writing.** The agent changes focus and goal through the memory profile's tools. `PreCompact` and `SessionEnd`
write the scope back so the next session starts where this one stopped.

**Decay.** Items not touched for a set number of turns leave the scope; they stay in declarative memory as
ordinary claims. The limit and the decay are parameters Morphogen tunes, starting from fixed defaults.

**Goals from the owner.** A goal proposed in the console waits on the bus's `owner` queue. The next session
reads it, writes it as an owner-attributed goal claim through the review lane (the owner approves it there), and
deletes the message; until step 3 lands, the session states it at the start instead.

## 4. Procedural memory

Skills are the productions. A skill is a folder under `.claude/skills/` (or a plugin's), and Claude Code chooses
one by its description. Substrate does not replace that choice; it gives it better evidence.

**Utility.** Each skill has a utility claim: how often it finished the task, at what token cost (from Bifrost),
and the verdicts Morphogen gave its output. `encoder-morphogen` and the Prometheus observer write these as DQV
measurements with PROV lineage. Working memory lists the skills relevant to the active goal with their utility,
so a poor skill is visible before it is chosen.

**Chunking (new skills).** When the episode log shows the same sequence of steps succeeding several times, the
agent drafts a skill for it on a branch. Morphogen judges the draft against the old way on held-out tasks (red
team first, A/A checks), and the result goes to kernel's review lane. The skill lands only with a passing verdict
and the owner's approval in review.

**Demotion.** A skill whose utility falls below its baseline over a window is flagged in review with its
evidence. Removal is a change like any other: judged, then approved.

## 5. Declarative and episodic memory

**Facts are claims.** Every fact is a kernel claim: attributed to a source, quoting its evidence, belief-scored,
scoped, valid-time and recorded-time stamped, written only through a change set. Conflicting claims stay side by
side; fusion picks a current value by authority (owner policy) or by reliability (a learned cell Morphogen
tunes).

**Activation.** Recall today ranks by BM25 and embeddings. A new kernel module, `activation`, reranks recall
results with three terms:

- base level: how recently and how often the claim was recalled or cited (from kernel's recall log);
- spreading: links from the entities in working memory;
- belief: the claim's fused belief score.

The weights start fixed. The module lands only if Morphogen judges it better than plain recall on held-out
questions about this repository and its stack; otherwise recall stays as it is.

**Episodes.** `encoder-interaction` reads each finished session (prompts, tool calls, outcomes, cost) and
writes one episode claim set with PROV lineage. Kernel's memory extractor proposes durable facts from episodes
into the review lane; nothing an episode suggests becomes a fact without review or a verifier.

## 6. Perception and motor

**Perception is encoders.** Each source reaches kernel through an encoder that writes claims under its own
role:

| Encoder | Reads | Writes |
| --- | --- | --- |
| self-encoder (kernel) | this repository and the clones | code, config and docs as claims |
| `encoder-backstage` | `catalog-info.yaml` | the map as `kk-tosca` claims (S-09) |
| `observer-prometheus` (kernel) | Bifrost metrics through Prometheus | cost, tokens and errors per window (S-05) |
| `encoder-morphogen` | Morphogen's evidence log | verdicts as DQV measurements (S-08) |
| `encoder-nomad` (new) | Nomad's event stream | allocations, failures, restarts; a failure also goes on the `triggers` queue |
| detectors (kernel M6-T0) | claims already in kernel | drift and conflict findings; each also goes on the `triggers` queue |

**Motor is actuators.** An action is declared in the ontology (name, inputs, the entity it changes, who may run
it) and every run is recorded as a claim. The first actuators:

- git: branch, commit, pull request (the `upstream` skill for kernel and Morphogen);
- Nomad: update or restart a job through its API, with an ACL token limited to the substrate namespace;
- the map: a catalog change as a pull request to `catalog-info.yaml`.

An actuator that changes a running system needs a passing Morphogen verdict or the owner's approval in the review
lane. Reads never do.

## 7. Cycle and hooks

The cycle is a Claude Code session. Hooks connect it to kernel; all of them run through `bin/` in the tools
container, so the host needs nothing more. Substrate adds to kernel's existing `SessionStart` and `PreToolUse`
hooks rather than defining a second set, and `scripts/point_harness.py` keeps the commands pointed at `bin/`.
The one hook substrate commits itself (`.claude/settings.json`) is the build-out's: at `SessionStart` it says
which step of this spec is next (`scripts/spec.py hook`).

| Hook | Command | What it does |
| --- | --- | --- |
| `SessionStart` | `kernel-mcp-hook` | injects the working-memory summary and the active goal |
| `SessionStart` | `scripts/spec.py hook` | names the next build-plan step while this spec is in place |
| `UserPromptSubmit` | `kernel-mcp-cue` | adds cues for entities the prompt names |
| `PreToolUse` | `kernel-mcp-hook` | kernel's existing checks before a tool runs |
| `PostToolUse` | `kernel-mcp-hook`, `async: true` | appends the step to the episode buffer without blocking |
| `PostToolUseFailure` | `kernel-mcp-hook`, `async: true` | records the failure against the skill in use |
| `PreCompact` | `kernel-mcp-hook` | writes working memory back before context is compacted |
| `Stop`, `SubagentStop` | `kernel-mcp-hook` | closes the step; marks the goal done or open |
| `SessionEnd` | `kernel-mcp-hook` | hands the episode to `encoder-interaction` |

Notes from Claude Code's hooks reference (https://code.claude.com/docs/en/hooks.md, read 2026-11-07):

- context goes in `hookSpecificOutput.additionalContext`, capped at 10,000 characters per string;
- `async: true` runs a command hook in the background, and its timeout is not enforced, so async hooks must end
  on their own;
- `onFailure` (`continue` by default, or `block`) needs Claude Code 2.1.295 or later; substrate keeps
  `continue` so a kernel outage never stops a session;
- `PostToolBatch`, `FileChanged` and `UserPromptExpansion` exist too; substrate does not use them yet.

## 8. Learning

Substrate learns in four loops. Every one ends the same way: a change is proposed, Morphogen judges it against
what runs now on evidence the changer cannot reach, and it lands only with a passing verdict (and the owner's
approval where it touches policy).

| Loop | What changes | Evidence |
| --- | --- | --- |
| Utility | skill and model-route preferences | task outcomes, verdicts, Bifrost cost |
| Chunking | new skills from repeated episodes | held-out tasks, old way vs new skill |
| Recall | activation weights, working-memory limits | held-out questions with known answers |
| Trust | the reliability cell that weighs sources in fusion | claims later confirmed or contradicted by verifiers |

Authority is not learned. Which source wins by policy is an owner claim; learning only adjusts reliability within
it. Morphogen's A/A checks (the same candidate judged twice) run before any loop's results are trusted, so judge
noise is measured rather than mistaken for improvement.

## 9. The organism

The mind above runs one session at a time. The organism is how many sessions, services and people work as one
business, laid out on Beer's Viable System Model.

| VSM system | Role | Substrate part |
| --- | --- | --- |
| 1 Operations | the work itself | skills and workflows acting on the business's systems |
| 2 Coordination | keep operations from colliding | the review lane, plus a `dispatcher` module that gives each entity one active session at a time |
| 3 Control | resources and performance now | kernel's MAPE-K loop over claims; budgets read from Bifrost costs |
| 3* Audit | check what operations report | Morphogen red team and kernel verifiers |
| 4 Intelligence | the outside and the future | source encoders, drift detectors (M6-T0), the planner role |
| 5 Identity | purpose and policy | owner claims: goals, policies, authority |

**Goals** are owner claims in a small vocabulary: what outcome, for which entity, by when, under which budget. A
goal is open until a verifier or the owner marks it met.

**Triggers** start sessions without a person: a detector finding, a failed allocation from `encoder-nomad`, a
goal past its date, or a schedule. Each is a message on the bus's `triggers` queue. The dispatcher reads that
queue and turns a message into a headless Claude Code session (a Nomad batch job on that runtime, a scheduled
task otherwise) with the goal and focus already in its working memory; a message is deleted only when its
session has started, so a crash leaves it to be read again (pgmq's visibility timeout).

**The owner** sees one console: the review lane, recent verdicts, spend, the stack and this spec's progress,
signed in with their kernel login. Anything that needs their decision arrives in the review lane with its
evidence.

## 10. Build plan

Each step adds one new cause of failure, and ends with a check anyone can run. [`build.yaml`](build.yaml) holds
the same steps with their status, checks and what each needs; the `build-out` skill works through it.

| # | Step | Where | Done when |
| --- | --- | --- | --- |
| 0 | The stack runs | substrate | `scripts/check.sh` passes on compose with Podman (console and bus included), then on Nomad |
| 1 | Verdicts become claims | `modules/encoder-morphogen` | each Morphogen verdict appears in kernel as a DQV measurement with lineage |
| 2 | The map becomes claims | `modules/encoder-backstage` | recall answers "what depends on bifrost?" from catalog claims |
| 3 | Working memory | kernel M6-T2, upstream PR (owner decides) | a new session states the active goal and focus without being told |
| 4 | Episodes | kernel's `encoder-interaction`, wired by substrate | a finished session appears as an episode; the extractor's proposals reach review |
| 5 | Activation | `modules/activation` | Morphogen verdict: better than plain recall on held-out questions, or the module is dropped |
| 6 | Skill utility | `encoder-morphogen` plus the observer | working memory lists relevant skills with success rate and cost |
| 7 | Skill promotion | chunking, judged | one skill drafted from repeated episodes passes judgment and lands through review |
| 8 | Motor | actuators, `encoder-nomad` | a failed allocation is noticed, a fix is proposed, judged and applied through Nomad's API |
| 9 | Organism | `modules/dispatcher`, triggers on the bus, goal vocabulary | a drift finding on `triggers` starts a headless session that closes it with a verdict, and the owner sees it in review |

Steps 1 and 2 need nothing from kernel's roadmap and come first. Step 3 changes kernel and waits for the owner's
decision.

## 11. Limitations

- **Untested on a real machine.** The stack has been validated by config checks and dry runs only. Step 0 comes
  before anything else here.
- **Kernel changes are the owner's call.** Working memory (M6-T2), identity resolution (M6-T9) and detectors
  (M6-T0) are kernel milestones; substrate proposes them upstream and waits.
- **Skill choice stays Claude Code's.** Utility can inform the choice through working memory; it cannot force
  one. If activation ignores it, the effect shows up as no change in verdicts.
- **The context budget is small.** 10,000 characters per hook string, and less is better; working memory has to
  be summarised hard.
- **Judges are models.** Verdicts are noisy; A/A checks measure that noise, they do not remove it. Small
  improvements may be indistinguishable from it.
- **Cost.** Judged runs, episodes and extraction all spend tokens. Bifrost measures it; budgets in control (VSM
  3) have to cap it.
- **Nomad is BUSL-1.1** (S-18). The organism must keep working on compose, so triggers have a non-Nomad path.
- **Single node.** Everything assumes one machine and one owner. Several owners or sites need federation with
  receipts, which this spec does not cover.

## 12. Sources

- The cognitive-architecture design this spec adapts: https://claude.ai/artifact/3P6yZSqSBGk8cJHsGH1XpV
- This repository, especially `DECISIONS.md` and `catalog-info.yaml`
- kernel (https://github.com/OpenReplicant/kernel): its decisions log and milestone 6
- Morphogen (https://github.com/OpenReplicant/Morphogen)
- Claude Code hooks reference: https://code.claude.com/docs/en/hooks.md (read 2026-11-07)
- pgmq v1.13.1: https://github.com/pgmq/pgmq (`INSTALLATION.md`)
- Caddy: the official image's docs on adding modules (docker-library/docs, `caddy/content.md`)
- Laird, Lebiere and Rosenbloom, "A Standard Model of the Mind," *AI Magazine* 38(4), 2017
- Beer, *The Heart of Enterprise*, Wiley, 1979 (the Viable System Model)
- IBM, "An architectural blueprint for autonomic computing," 2005 (MAPE-K)
- W3C Data Quality Vocabulary (https://www.w3.org/TR/vocab-dqv/) and PROV-O (https://www.w3.org/TR/prov-o/)
