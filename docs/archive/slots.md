# Slots: how the parts of a harness are named, filled and judged

Written 2026-11-16 from a conversation with the owner, for a later session that did not see it. It is thinking,
not a build plan: nothing here is built beyond what the "today" column says, and `docs/handoff.md` still sets the
order of work (slots are its item 7). The owner's words are quoted where they set the direction.

## The idea

Owner: "everything has 'roles' that they fill 'slots' in need of ... any of these slots can get 'influenced or
filled by Morphogen' which will then govern its selection & maintenance."

- A **slot** is a place in a loop where one part can be swapped while the rest stays fixed. It has a contract:
  what goes in, what comes out, what it may not see, what cost it reports.
- A **role** is what a filler does in a slot. One part can fill several roles.
- A **type** is the form a filler takes: a prompt, a skill, a hook, a model, a service, a parameter, a script.
- These are separate axes. One slot takes several types (recall can be a notes file, a vector index or a skill).
  A catalog entry says: fills slot X, has form Y, has verdict Z.

## The loop and its slots

Something arrives; the agent decides what to look at; something decides what to do; it acts; the result is
checked; a record is kept; later, records change the agent.

| When | Slot | What it does | Today |
| --- | --- | --- | --- |
| Each step | View | turns a raw observation into what the handler sees | the lookups page view (`observation:` in `environment.yaml`) |
| Each step | Context | what of the episode so far is shown, and what is cut | the append-only log with a window |
| Each step | Recall | what is fetched from outside the episode | `notes/`, Workbench search, `packages/papers/lookup.py` |
| Each step | Router | which handler takes this step | `select: cost-order` |
| Each step | Handler | decides: a rule, a routine, a model with instructions, a person | one model handler |
| Each step | Control | the shape of the stepping: act directly, plan first, retry after failure | `max_steps` only |
| Each step | Tools | which actions are offered and how they are described | search, fetch, answer, hand off |
| Each step | Check | stops or corrects an action before it lands | the quote gate in the papers reader |
| Between episodes | Keep | what is written down from an episode | the fetched-page record; nothing learned |
| Between episodes | Learner | turns records into changed parts | the routine learner (parked); GEPA through Morphogen |
| Outside the agent | Outcome, Meter | the score and the cost | the scorer and the gateway: the judge's, never a candidate's |

The list is open. Owner: "potentially there are more slots yet to be discovered/standardized." A new slot is
added when a part turns up that fits none of these and can be swapped on its own.

## What makes something a slot

1. A contract test that passes or fails without a model's opinion (`scripts/contract.sh INTERFACE FILLER`).
2. An empty default, so the smallest agent is one handler with every other slot empty.
3. Two fillers can be judged against each other with everything else held fixed.

A slot is real when it has two fillers and one verdict. Until then it is a name.

## Fillers have slots of their own

Owner: "'claude code' fills roles and has many slots of its own: files, skills, MCP servers, hooks, models ...
recursive structure modeling allows us to compare slot-fillers for compatibility and work-arounds/gap-fillers ...
claude code could be swapped with Pi or Hermes or Codex or some custom script/service."

- A filler is a system too, with its own slots. Claude Code fills the Handler role here, and inside it: skills
  fill Recall, hooks fill Check, `CLAUDE.md` is instructions, MCP servers are Tools, the model is a sub-slot.
- Comparing two fillers of one slot is comparing their inner slots. Where one has a slot the other lacks, that is
  a gap; a gap is closed by a work-around (another part filling the missing role from outside) or left open and
  recorded.
- This is the same map at every level, which is why self is not a special case.

## Workbench as the kernel

The owner called Workbench a "kernel", a "central nervous system". In slot terms it fills Recall and Keep for
the whole harness, and it is where the slots, their fillers and their verdicts are recorded. S-120 made it part
of Substrate for that reason.

## Inside Keep and Recall: encoders, processors, decoders

Owner: "i built a custom store because i wanted modular ingestion and processing ... back to my common model of
encoders, processors, decoders", and on a published wiki-and-graph memory whose compile step cost money:
"that's where deterministic & low-cost ingestion/processing flips the bill."

The store's own part is not the claims table (many systems have one, S-120). It is that what goes in, what is
done to it and what comes out are modules that can be swapped and judged. Keep and Recall have inner slots:

| Inner slot | What it does | Today |
| --- | --- | --- |
| Encoder | a source or a reading into claims: subject, field, value, quote, span, time | extractors; a sensor's `encoder` (`docs/contracts/environment.md`) |
| Processor | claims into claims, between episodes: link, supersede, retract, expire, promote, infer | `reasoner`, `drift`; the review lane |
| Decoder | claims into what a reader sees: a page, a search result, a path through links, an export | search with relations, `trace.sh`, the Map view, `catalog-info.yaml` |

**The table already has the places.** `wb.claim` (`workbench/workbench/sql/001_core.sql`) carries `valid_from` and
`valid_to` beside `observed_at`, a `status` of current, superseded, retracted or disputed, `superseded_by`,
`confidence`, `span` and a `hash`. What is missing is modules that fill and use them, so a gap is closed by a
module and not by a change to the store.

**The Agent Memory Atlas's seven marks as modules** (source `agent-memory-atlas` on the map; whether Workbench
earns each mark is not checked yet):

| Mark | Kind of module |
| --- | --- |
| Bi-temporal validity | an encoder that sets `valid_from`/`valid_to`; a decoder that asks "as of when" |
| Rejected-value tombstone | a processor that keeps a retracted value so the same value is not learned again |
| Explicit trust state | a processor that promotes or disputes; the `status` and `confidence` it writes |
| Scope enforced in retrieval | a decoder that filters by domain before ranking, not after |
| Append-only mutation audit | the store's own (claims are superseded, not edited) |
| Human review surface | the review lane |
| Negative retrieval assertion | a contract test on a decoder: this must not come back |

**Deterministic first, a model last.** An encoder is code when the source has structure (the paper catalog: 9,466
papers, no model). A model is used only for what code cannot do, and only on what changed (the source's hash).
Forgetting, correction and consolidation are processors; each can be judged like any filler: does it cost
accuracy, does it save tokens.

**A default to test, not yet decided:** pages and a typed graph over the claims, read with two tools (find a
node, follow its links), after LangChain's OpenWiki post of 2026-10-28. Its backing is one vendor's own test on a
synthetic library against keyword search only, with the compile cost left out. The comparison worth judging here
has four arms on connected questions: keyword search, pages written by a model, pages made from claims by
template with no model, and either with the graph.

## The environment's own slots

The environment (`docs/contracts/environment.md`) is a filler too, with slots of its own. Owner: "each
'environment' might be something Morphogen could attach to as an external fitness/feedback function ... we make
them customizable units through interface contracts."

| Slot | What it does | Today |
| --- | --- | --- |
| Case source | where cases come from: a benchmark, a process's history, a generator | `packages/lookups/cases/` |
| Sensors and encoders | readings into claims (the View above, seen from the environment's side) | the lookups page view |
| Actions and gate | the declared action kinds, each `free`, `propose` or `deny` | search, fetch, answer, hand off |
| State machine | states, transitions, the actions allowed in each; optional, one state by default | none |
| Stepping mode | who runs the loop (table below) | owned |
| Replay recorder | what is read from outside is recorded and replayed in judged runs | fetched pages |
| Scorer panel and verdict rule | the scorers, and which metric decides and which only bound | one scorer, one deciding metric |

**Stepping modes.** Coding agents run their own loops, but most can be watched and gated step by step:

| Mode | Who runs the loop | What the environment sees | For |
| --- | --- | --- | --- |
| owned | the route is asked at every step | every step, and who took it | our handlers, routines below a model |
| observed | the agent's own loop; the environment's actions served as an MCP server, gated by the agent's hooks (Claude Code's `PreToolUse`, the Agent SDK's permission callback, Codex's approval modes) | every tool call | Claude Code, Codex, Pi, Hermes |
| black-box | the agent | only the end state | anything else, such as a vendor's service |

**State machines** are the bridge to process work: a process is states and transitions, an action can be `propose`
in one state and `deny` in another, and a scorer can score the path (did it pass through approval), not only the
end. BPMN and SCXML are the standards; a library is picked from the catalog when the first process environment
needs one.

**Scorers as a slot with several fillers**, in people's custody:

- A panel (exact match, a test runner, a model grading on a fixed rubric, a person on a sample) is allowed only
  with the verdict rule fixed before the run: one metric decides, the others bound. Otherwise more scorers are
  more chances to pass by luck.
- Disagreement between scorers on a case sends it to a person or drops it, and shows which scorer is weak.
- A scorer is admitted by its own contract test: the do-nothing and constant agents score the stated floors,
  the dev answers replayed score 1, it agrees with a person's labels on a small calibration set, and it resists
  the red-team cheats.
- **Generated scorers:** a scorer-writing agent is a separate role. It runs on the judge's side (the judge
  user), and what it writes reaches the base only by the owner's password-gated advance (S-121), so the agent
  being judged never writes or picks its own scorer. Reusable scorers (exact match, F1, state diff, tests, a
  rubric with a fixed grader model) are catalog entries; most of the case-and-scorer kit is this library.
- Morphogen as the fitness function: `optimize.Gepa` already uses the judge's measurement on the search set as
  GEPA's evaluator. With the scorer as a declared slot, any optimizer gets fitness from the same place and never
  sees the held-out set.

None of these seven is built beyond the "today" column, and the rule above holds: a slot is real when it has two
fillers and one verdict. Three wraps make three real first: a coding task with tests (observed mode), a support
task with a simulated customer (a rubric scorer), a process-history set (a state machine, late outcomes).

## Morphogen's place

Morphogen is not a slot filler. It decides which filler a slot keeps: a filler is admitted when it passes the
slot's contract test and trusted when it has a verdict. Optimizers (GEPA's `optimize_anything`, Optuna, a coding
agent) fill the Learner slot: they propose, on a practice set, and the judge decides on cases they did not see.
Morphogen already drives `optimize_anything` this way (`morphogen/optimize.py`, class `Gepa`).

## Cognitive terms

Useful as names a reader recognises, kept as mappings in the vocabulary and out of the code: working memory is
Context; long-term memory is Recall plus Keep; fast and slow is the Router trying a cheap routine before the
model; self-monitoring is Check plus handing off. The CoALA paper (Sumers and others, 2023) is the framing most
readers know.

## Papers as fillers

Most agent papers are a filler for one or two slots plus a claimed gain. From memory, to be checked against the
catalog before quoting: Agent Workflow Memory is Keep plus Recall; Reflexion is Learner plus Recall; ReAct is
Control; Voyager's skill library is Keep, Recall and Check; MemGPT is Context plus Recall; model cascades are
Router. "Which slot" is the catalog's main key.

## Open questions, the owner's

- Memory as one slot or two. Proposed: two (Recall, Keep); they run at different times and papers vary them
  separately.
- Who owns a slot's contract. Proposed: the environment's side, in people's custody, so a candidate cannot
  loosen its own check.
- Learned state. A filler that learns during a judged run breaks the paired comparison. Proposed: learning
  happens outside judged runs and the frozen result is what is judged, as `notes/` works now.
- Topology (which slots are wired, in what order). Proposed: configuration of the route, not code, and left
  until parameter and component swaps have verdicts.

## Where to start

Three slots, because the evidence here points at them: Tools and View (the 3B model ignored instructions and
followed its tools, S-110); Recall plus Keep (the Agent Workflow Memory reproduction, handoff item 5); Router
(routines; the first attempt learned too few rules, S-109).
