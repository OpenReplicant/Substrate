# Multi-process cognition: a proposal

Status: **adopted into the spec as section 10, steps 17 to 21 (S-74, 2026-11-10)**; the spec is the
authority, and this is the longer write-up. It widens a dual-process brief the owner handed in (two tiers) to N
tiers with an idle tier, from the owner: "multi-process cognition where there's escalating tiers/routes of response to
inputs, as well as an idle tier. Inputs are more than just 'LLM prompt' but anything the system wants to tune
into and build responses/handlers for", and "we have N tiers, not just 4".

## 1. The idea

The system subscribes to **inputs**: any stream of events it chooses to tune into. Each input is handled by the
cheapest **handler** that can handle it well. A handler that can't passes the input up, with a reason, to a
dearer one. Whatever a dear handler works out is then **compiled down** into a cheaper one, and Morphogen
judges whether that helped, on inputs the change was not tuned on. When nothing needs attention, the **idle
tier** spends a budget on the work no input asked for: compiling, practising, pruning, and choosing what to
tune into next.

Over time, inputs get resolved lower down. Cost falls and outcomes hold. Nothing is trained into weights, and
everything learned is a readable component with claims behind it.

This is a learning method in the sense of spec section 1 ("from asking a model to knowing") and section 8's
held ideas: the loop that turns slow model work into faster, checkable parts. It is not a new part of
substrate. Dual-process (a small model deferring to a large one) is its two-tier special case.

## 2. Terms

| Term | Means |
| --- | --- |
| **Input** | one event on a stream: a game state, a new email, a drift gap, a failing check, a hook firing, a timer, a prompt |
| **Stream** | a kind of input the system has subscribed to: its source, the shape of its events, and how an outcome is later known |
| **Handler** | a component that takes an input and returns an **answer** or an **escalation**. A script, a rule, a model with a prompt and knowledge files, a Claude Code session, a person |
| **Rank** | a handler's place on the ladder, by measured cost per input (time, money, a person's attention), not by declaration |
| **Route** | the path an input takes through handlers: which one sees it first, and where each may send it |
| **Escalation** | "not me": a reason, and optionally where to go next |
| **Compile down** | turning an answer from rank *k* into a handler (or a change to one) below *k* |
| **Outcome** | what happened after the answer: the game score, the check passing, the person accepting, editing or redoing the work. This is ground truth; another handler's opinion is not |

## 3. N tiers, not four

There is no fixed ladder. Ranks are handlers sorted by what they cost, so there are as many as there are
handlers. Here is a ladder that might grow, cheapest first:

1. a reflex: a hook, a script, a lookup (no model)
2. a rule over claims (the reasoner, step 7; learned rules, section 8)
3. a recipe: a small local model with a knowledge file
4. a mid-size model with more context
5. a large model
6. a Claude Code session with tools
7. several handlers asked at once, escalating when they disagree
8. a specialist person (a teammate, a business's staff member)
9. the owner (the review lane)

Some consequences:

- **Adding a tier is adding a handler.** Retiring one is `retire_item`. The ladder is on the map, like everything
  else, and changes the same way.
- **Several handlers can share a rank**, each specialised for part of a stream. The router picks between them.
- **Escalation can skip.** A handler can send an input anywhere above it, or fan it out. "Next rung up" is the
  default, not a rule.
- **Ranks move.** A handler's rank is a measurement (its observed cost per input), so a model that gets cheaper,
  or a handler that grows its knowledge file and gets slower, moves on its own.
- **People are ranks too.** That's why the review lane, with nothing new added, is the top of every ladder.
- **The router is a handler.** It can be tuned, compiled into and judged like any other, and its rules are
  claims.

## 4. The escalation contract

Every handler, whatever it is, keeps one contract:

```
handle(input) -> answer { value, confidence, cost }
              |  escalate { reason, to? , cost }
```

Every call is recorded: the input, the handler, its answer or escalation, its cost, and later the outcome. Each
of these is a claim, attributed to the handler, so the history can be queried, held out and compiled from. A
handler that breaks the contract (answers with no confidence, or calls another handler without saying so) is
a defect, and Morphogen's red team should look for it first (section 7).

## 5. Compiling down

When rank *k* answers an input and the outcome is good, the idle tier (or the escalation itself) proposes a
change below *k*. The change can be:

- a line in a knowledge file or a recipe (rank 3 learns what rank 5 knew)
- a rule the reasoner applies (a pattern seen often enough to state)
- a script or hook (a recipe that has become fully predictable becomes code)
- a routing rule (inputs like this one go straight to rank *j*)

Each is a change to a component, so section 7's first row decides it: Morphogen's verdict, on held-out inputs,
against what runs now. Each kept change cites the escalations it came from. Each rejected one stays a negative
result, so it isn't tried blind again.

Compiling up also happens. A handler whose escalation rate climbs, or whose outcomes drop, gets its inputs
routed higher until it's fixed or retired.

Lineage: Soar's chunking, ACT-R's production compilation, Expert Iteration (Anthony et al., 2017), and
distillation in general.

## 6. The idle tier

The idle tier is not a rung. It's how the system spends a budget (time, money, compute) when no input is
waiting, or whatever share of time the owner sets. Its jobs, each a handler of its own on a timer stream:

- **Replay**: go through recent escalations and propose compile-downs (section 5).
- **Practise**: play fresh cases where a stream allows it (game seeds), at a low rank, to find what escalates.
- **Prune**: retire handlers that never fire, or that cost more than they save.
- **Re-rank**: re-measure handlers' costs, and move them.
- **Work the map**: thin parts and open gaps, the questions an interview would ask.
- **Attend**: choose which streams to subscribe to, drop or sample down. This is where "what the system wants
  to tune into" gets decided. A new subscription is a map change, so it goes to the review lane, at least at
  first.

The spec's held ideas land here: episodes from sessions, skill utility and promotion, and a dispatcher that
starts headless sessions. Workbench already has the plumbing: pg_cron for timers, pgmq for jobs, and NOTIFY for
live events.

## 7. Measuring it, and the cheats

**Per stream:** inputs by resolving rank, cost per input, outcome score, and escalations per input. Success means
the resolutions move down while outcomes hold or rise, judged on held-out inputs (game seeds, or time windows
for a person's streams, as step 13 does for a business's).

**The cheats this invites**, for the red team to try first:

- a router or handler that never escalates (cost falls, outcomes fall)
- one that always escalates (outcomes rise, cost rises; a candidate tuned only on outcomes would do this)
- calls up the ladder the judge can't see: a handler that quietly asks a bigger model inside itself, so it
  looks cheap
- confidence that doesn't track outcomes
- the idle tier practising on held-out seeds or windows
- outcomes taken from another handler's opinion instead of what happened

**Counting from outside.** Morphogen's `otel` observer already adds up Claude Code's cost and tokens outside the
candidate (its README, "Observers"). Other models need the same, which is the Bifrost option's stated trigger:
"cost must be measured outside the agent, or several providers routed" (spec section 8). A judged run would
route every model call through the gateway, and count calls the gateway didn't see as a failure. Any change
to how Morphogen counts goes upstream, red team first (CLAUDE.md, the `upstream` skill).

## 8. What exists, what's new, where it lives

| Piece | Exists? | Lives in |
| --- | --- | --- |
| Rank 0 handlers (hooks, scripts) | yes: `.claude/settings.json` hooks, extractors | substrate |
| Top rank (a person) | yes: the review lane, `wb.decision` | Workbench |
| Rules over claims | yes: the OWL 2 RL reasoner (step 7) | substrate's plugin |
| Timers, jobs, live events | yes: pg_cron, pgmq (`wb_jobs`), NOTIFY to SSE | Workbench |
| Cost counted outside the candidate | for Claude Code: Morphogen's `otel` observer | Morphogen |
| **Stream** and **input** as content types | new; generic (any CMS could subscribe to a feed) | Workbench, or a generic plugin; OCEL 2.0 (step 12) may be its event shape |
| **Handler** and **route** as content types, and the escalation record | new; generic beyond substrate | a plugin (substrate's at first) |
| The contract (`handle -> answer \| escalate`) and a runner | new | a small library; a separate repo once a second user needs it |
| Model handlers through a gateway | an option (Bifrost v2.3.2, restore from `a00fb61`) | brought back through section 5 |
| Escalation counting in judged runs | partly (otel) | Morphogen, upstream |
| The idle scheduler | new | substrate's plugin, on pg_cron |
| A game, and its outcome score | new | its own repo or a plugin; chosen through section 5 |

## 9. A first cycle

Recommended: a game first, because its outcome is honest, fast and free, and its seeds give unlimited held-out
cases. Build it the general way, though: the game is just a stream of events with a score as its outcome, so
the second stream needs nothing new.

1. Pick the game through the `research` skill (an existing environment with seeds and a score, permissive
   licence), and a small and a large model through the gateway.
2. Three ranks: a reflex (a script with no knowledge), a small model with an empty knowledge file, a large
   model. Every call is recorded (section 4).
3. Play N seeds. Escalations pile up.
4. Idle tier: replay them, propose one compile-down (a knowledge-file change for the small model).
5. Morphogen judges it on seeds it hasn't seen: score, cost per game, escalations per game, with an A/A check.
6. Repeat a handful of times. Done when held-out score holds or rises while cost and escalations fall, with no
   regressions and at least one refused cheat in the evidence log (the brief's bar).

After that, a second stream with a person at the top. This repo's own review lane is the cheapest to try (its
outcomes are the owner's decisions). Then the personal assistant's streams (email, calendar), where outcomes are
accepted, edited, redone or ignored, and privacy rules come first (settings by name, gitleaks, local models for
personal data).

## 10. Draft for the spec

As drafted; the spec's section 10 is what was adopted, with steps 17 to 21:

> **Multi-process: inputs handled at the cheapest rank that can (S-xx).** Substrate subscribes to streams of
> inputs (anything it chooses to tune into, not only prompts) and handles each with the cheapest handler that
> can: a ladder of any length, from a script to a rule, a small model, a large model, a session, a person, with
> the review lane at the top. A handler answers or escalates with a reason. Every call and its outcome is a
> claim. What a dearer handler works out is compiled into a cheaper one (a knowledge file, a rule, a script, a
> route), and Morphogen keeps it only if it helps on inputs it was not tuned on, by outcome, never by another
> handler's opinion. An idle tier spends a budget on replay, practice, pruning, re-ranking and choosing what to
> attend to. Model calls are counted outside the candidate. Done when, on a game stream, held-out score holds
> while cost and escalations per game fall over judged cycles, and the red team's cheats are refused.

Possible steps: (a) streams, handlers and the escalation record as content types; (b) the gateway back, with
calls counted outside the candidate; (c) a game stream and one judged compile-down; (d) the idle tier; (e) a
person's stream (the review lane), then the assistant's.

## 11. The owner's decisions

1. **Placement.** Recommended: a section of the spec and steps of their own, with dual-process as the two-rank
   case. It would also cover "learning methods from a catalog": each compile-down form (section 5) is one.
2. **Order against step 10.** Recommended: (a) and (b) before step 10. Streams and the escalation record are
   what step 12 needs for events, so the business steps reuse them instead of growing their own.
3. **Models and budget.** Which small and large models (and whether a local one, for privacy later), and a
   monthly ceiling for model calls and for the idle tier.
4. **How much lands on its own.** Recommended at first: compile-downs land on a passing verdict; new
   subscriptions, new ranks and anything touching a person's stream go to the review lane.
5. **The assistant's first streams**, when it's time.
