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
   only with a Morphogen verdict, and with the owner's approval when the automation level asks for it (section 9a).
5. **One of each.** One store, one judge, one gateway, one control plane, one bus, one hook set per event. No
   module keeps a private database; the bus is a database in the same Postgres, not a second server.
6. **Nothing on the host but git, python3, the engine and Claude Code.** Every new command runs in
   `substrate-tools` (S-19).
7. **Organization is the owner's; structure is free to change under judgment.** What makes the system itself
   (purpose, goals, policy, who decides what, kernel's invariants) changes only through the owner. What
   currently realises it (code, config, skills, model routes, where services run) changes whenever a verdict
   says the change fits better.
8. **Small defaults, open slots.** Each slot (runtime, engine, secrets, map view, model provider) has one default
   that is tested on a fresh machine; the others stay behind the same interface, marked untested until their own
   check passes. A second default is added only when a goal needs it.
9. **Automated by default, reversible always.** The automation level (section 9a) decides how much reaches the
   owner; at every level each decision is attributed and can be undone. What principle 7 calls organization is
   never automated.

### Software as a process, not a product

A software factory makes software the way a plant makes a car: built, checked at a gate, shipped, then someone
else's concern. The factory and its product are separate things. Substrate has no product in that sense. The
running system is the software, and its work is keeping itself fitted to its purpose; code is its current
structure, not its output, and there is no "done", only the next adaptation. In Maturana and Varela's terms a
factory is allopoietic (it produces something other than itself) and substrate is autopoietic (it produces and
maintains itself), and principle 7 is their split between organization and structure. Substrate's first
distribution being the system minding itself (S-10) follows from this: self-reference is the normal case.

Self-reference is the core, not the limit. Agents today take actions to achieve goals; substrate changes its own
structure to achieve goals (owner, 2026-11-08). The same organism can become an assistant, a business's brain or a
player of a game by taking on different goals and growing the structure they need: new encoders for what it must
perceive, new actuators for what it must change, new skills for how. Its first goal is keeping itself fitted, so
the loops are proven on itself before they are pointed outward.

### The self-model has two faces

A self-maintaining system needs a model of itself in two halves, and the gap between them is where all of its
work comes from:

| | Intended (the blueprint) | Observed (the structure) |
| --- | --- | --- |
| Says | what the system is meant to be: parts, owners, relations, limits, the documented process | what it actually is: what runs, what calls what, what happened, what it cost |
| Written by | people, as declarations they own | encoders and observers, as measurements |
| In substrate | `catalog-info.yaml` (Backstage's format), owner claims, process models (BPMN) | code (self-encoder), Nomad and Prometheus (observers), event logs, episodes, Morphogen's measurements |
| Trust (Morphogen's levels) | stated | measured |
| Alone it becomes | documentation that rots | a system that only preserves whatever it happens to be |

Runtime reconciliation, whether a declared job is actually running, is Nomad's and is not rebuilt here (S-27).
The observed calls come from OpenTelemetry (S-28), with `service.name` equal to the catalog's component name, so
the two halves join by name. The console's Map draws intended, observed and their difference (S-29).

Both halves are claims in one store, attributed and scoped, which is what makes them comparable: a detector
asks where they disagree (a dependency used but not declared, a declared owner who never acts, a process path
taken that the model does not have). The same pattern already appears three times: Kubernetes-style
controllers (spec against status), kernel's conformance checking (documented process against the event log,
D-50), and Morphogen's structure (intended cells against observed traces).

A gap can close in **either direction**, and choosing which is a decision, not a computation. Practice may be
brought back to intent (a fix, judged by Morphogen), or intent may be revised to match practice that turned out
better (kernel's process learner proposes this, D-76). The review lane is where that choice is made. A system
that always enforced its blueprint would be rigid; one that always accepted what it observed would have no
identity. Keeping both, and deciding between them on evidence, is what lets it change without ceasing to be
itself.

The blueprint is a **catalog of things**: what exists, who owns it, what it is for, how it relates. Backstage's
catalog format was the first one used, because it is the most widely used way owners declare systems beside their
code (`encoder-backstage` reads it into claims, kernel D-100). Backstage itself, the server, was not built for
this: a catalog here is any kind of thing (a service, a customer, a process, a game's rules), and its home is
kernel, where it is claims with provenance that recall and kernel's MCP already answer. So the catalog lives in
kernel, a file is one way to write it, and a browsing view is an optional slot (step 13). The blueprint alone
does not observe, so on its own it drifts from reality; substrate supplies the other half and the loop between
them (encoders turn declarations into claims; observers supply what is; detectors, triage and the review lane
close the gap).

## 2. Module map

Each module of the cognitive design maps to a part substrate already runs or to a kernel module it adds. Nothing
gets its own store: every memory is claims in kernel's Postgres, written by change sets under a role. Work and
notices between parts travel on the bus; facts never do.

| Cognitive module | Substrate part | State today |
| --- | --- | --- |
| Cycle (decide, act, observe) | A Claude Code session, with hooks run through `bin/` in the `substrate-tools` container | Runs |
| Working memory | Kernel's agent working-memory scope (M6-T2), read and written through the kernel MCP memory profile | Planned in kernel |
| Declarative memory | Kernel claims plus recall (BM25 and embeddings, D-60, D-61); a new `activation` module reranks recall | Claims run; activation new |
| Associations (graph) | pgGraph over `kernel.current_edge`, in kernel's Postgres image | Extension in the image; the graph module new |
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
| Coordination (triage) | A `triage` agent with its own reviewer login: settles review items at the automation level, each decision attributed and reversible (section 9a) | New (step 12) |
| The owner's view | The console (S-22) behind the front door (S-20), signed in with a kernel login | Runs |
| Secrets | The secrets slot (S-31): `.env`, or OpenBao with policies and an audit trail | Runs |

Graph questions (what depends on what, who is near whom, paths and neighbourhoods) go to **pgGraph**, which
kernel's Postgres image carries (kernel D-94, S-24): a rebuildable graph over `kernel.current_edge` (D-86),
queried as the calling role so row-level security, and with it clearance, still applies. Storage stays SQL
(kernel D-08).

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
team first, A/A checks), and the result goes to kernel's review lane. The skill lands only with a passing verdict,
and with the owner's approval in review when the automation level asks for it.

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
- spreading: links from the entities in working memory, read as pgGraph neighbourhoods;
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
| `encoder-backstage` | `catalog-info.yaml` (the first catalog format; others later, step 13) | the map as `kk-tosca` claims (S-09) |
| `observer-prometheus` (kernel) | Bifrost metrics through Prometheus | cost, tokens and errors per window (S-05) |
| `observer-prometheus` (kernel) | the OpenTelemetry collector's service graph through Prometheus | observed calls between parts per window (S-28) |
| `encoder-morphogen` | Morphogen's evidence log | verdicts as DQV measurements (S-08) |
| `encoder-nomad` (new) | Nomad's event stream | allocations, failures, restarts; a failure also goes on the `triggers` queue |
| detectors (kernel M6-T0) | claims already in kernel | drift and conflict findings; each also goes on the `triggers` queue |

**Motor is actuators.** An action is declared in the ontology (name, inputs, the entity it changes, who may run
it) and every run is recorded as a claim. The first actuators:

- git: branch, commit, and a pull or merge request on whichever forge the repository lives on (GitHub, Forgejo,
  Gitea, GitLab; S-25), with the `upstream` skill for kernel and Morphogen. A forge's merge button is not an
  approval path; approvals stay in the review lane and Morphogen's verdicts;
- Nomad: update or restart a job through its API, with an ACL token limited to the substrate namespace;
- the map: a catalog change as a pull request to `catalog-info.yaml`.

An actuator that changes a running system needs a passing Morphogen verdict or the owner's approval in the review
lane. Reads never do.

## 7. Cycle and hooks

The cycle is a Claude Code session. Hooks connect it to kernel; all of them run through `bin/` in the tools
container, so the host needs nothing more. Substrate adds to kernel's existing `SessionStart` and `PreToolUse`
hooks rather than defining a second set, and `kk up --commands-dir bin/` (kernel D-95) points the commands at `bin/`.
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
| 2 Coordination | keep operations from colliding | the review lane and the `triage` agent (section 9a), plus a `dispatcher` module that gives each entity one active session at a time |
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
evidence, and what triage settled is listed beside it with an undo.

### 9a. Triage and the automation level

Beer's system 2 and 3 exist to absorb variety, so that system 5 sees only what needs its judgment. A review lane
that sends every item to one person fails the way the first run did (2026-11-08): four of five gaps were
telemetry noise, and they were approved without being read. Triage is the part that absorbs that variety.

**Order.** Noise is fixed where it starts (an observer query, an encoder) rather than declined again and again;
what still arrives goes to triage first; only what triage escalates reaches the owner.

**The triage agent** is a kernel agent (`urn:kk:agent:triage`) with its own reviewer login. Kernel already
refuses approval by a change set's submitter (KK025) and records who decided (`decided_by`), so triage never
settles its own proposals, and every decision is attributed to it. For each item it writes a recommendation with
its evidence (the claims, the code line, the observation) and a confidence.

**The automation level** is a setting (`AUTOMATION` in `.env`, read through the console too):

| Level | Triage settles | Reaches the owner |
| --- | --- | --- |
| `full` (default) | everything outside organization: approves or declines with its reason | escalations: low confidence, conflicting evidence, or an item it cannot classify |
| `assisted` | nothing; it recommends | every item, with the recommendation and evidence first |
| `manual` | nothing; it does not run | every item as it is |

**Reversible always.** An approval triage gave is undone by retracting what it applied (kernel never deletes; a
status records the retraction and who made it); a decline is undone by resubmitting. The console lists triage's
recent decisions with an undo for each, and an undo is itself a recorded decision that triage learns from.

**Never automated, at any level** (principle 7): owner claims (goals, policies, authority), clearance grants,
kernel's invariants and schema, licences, and spending above the budget the owner set. These always reach the
owner.

**Learning.** Triage's recommendations are a cell Morphogen judges: the owner's undos and escalation answers are
held-out evidence of where it was wrong. A rising undo rate lowers what it settles alone.

## 10. Build plan

Each step adds one new cause of failure, and ends with a check anyone can run. [`build.yaml`](build.yaml) holds
the same steps with their status, checks and what each needs; the `build-out` skill works through it.

| # | Step | Where | Done when |
| --- | --- | --- | --- |
| 0 | The stack runs | substrate | `scripts/check.sh` passes on compose with Podman (console and bus included), then on Nomad |
| 1 | Verdicts become claims | `modules/encoder-morphogen` | each Morphogen verdict appears in kernel as a DQV measurement with lineage |
| 2 | The map becomes claims | `modules/encoder-backstage` | recall answers "what depends on bifrost?" from catalog claims, and the first intended-against-observed gap reaches review |
| 10 | A fresh-machine test | `scripts/fresh.sh` | a clean checkout in a throwaway container bootstraps and passes `scripts/check.sh` with no manual step |
| 11 | One default per slot | substrate | the defaults (compose, Podman, `.env`) are the only tested path; the others keep their interfaces, marked untested |
| 12 | Triage and the automation level | `modules/triage`, the console | at `full`, a noise gap is settled by triage, listed in the console with an undo, and the undo restores it |
| 13 | The map without Backstage | substrate, kernel's MCP | catalog questions are answered from kernel claims with Backstage off; the view is an optional slot |
| 3 | Working memory | kernel M6-T2, upstream PR (owner decides) | a new session states the active goal and focus without being told |
| 4 | Episodes | kernel's `encoder-interaction`, wired by substrate | a finished session appears as an episode; the extractor's proposals reach review |
| 5 | Activation | `modules/activation` | Morphogen verdict: better than plain recall on held-out questions, or the module is dropped |
| 6 | Skill utility | `encoder-morphogen` plus the observer | working memory lists relevant skills with success rate and cost |
| 7 | Skill promotion | chunking, judged | one skill drafted from repeated episodes passes judgment and lands through review |
| 8 | Motor | actuators, `encoder-nomad` | a failed allocation is noticed, a fix is proposed, judged and applied through Nomad's API |
| 9 | Organism | `modules/dispatcher`, triggers on the bus, goal vocabulary | a drift finding on `triggers` starts a headless session that closes it with a verdict, and the owner sees it in review |

Steps 1 and 2 need nothing from kernel's roadmap and come first. Steps 10 to 13 come next (owner, 2026-11-08):
every step from 3 on adds a source of review items, so triage comes before them, and a fresh-machine test before
anything is built on the stack again. Step 3 changes kernel and waits for the owner's decision.

## 11. Limitations

- **One tested path.** The stack first ran on a real machine on 2026-11-08 (compose, Podman 4.9), after four fixes
  no dry run had caught. Step 10 keeps it that way; other slot choices are untested until their checks pass.
- **Full automation is a bet on triage.** At the default level most items are settled without the owner. Undo,
  attribution and the never-automated list bound the damage; the undo rate measures it.
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
- pgGraph v1.2.1: https://github.com/evokoa/pggraph (installation, administration and security guides)
- Caddy: the official image's docs on adding modules (docker-library/docs, `caddy/content.md`)
- Laird, Lebiere and Rosenbloom, "A Standard Model of the Mind," *AI Magazine* 38(4), 2017
- Beer, *The Heart of Enterprise*, Wiley, 1979 (the Viable System Model)
- IBM, "An architectural blueprint for autonomic computing," 2005 (MAPE-K)
- W3C Data Quality Vocabulary (https://www.w3.org/TR/vocab-dqv/) and PROV-O (https://www.w3.org/TR/prov-o/)
