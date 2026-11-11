# Handlers: a Workbench plugin for streams, ranked handlers and the record of every call

A plugin for any Workbench, written so it can leave with Workbench: nothing in it names the plugin or system
that uses it, and a test checks that.

## What it is

A **stream** is a kind of input something has subscribed to: its source, and how an outcome is known later. Each
**input** goes up a ladder of **handlers**. Each handler answers (a value and a confidence), escalates (a reason,
and where to, if it knows), or, for a person, waits. Every **call** is recorded with what it returned, its cost
and, once the input's outcome is known, whether the answer matched it. A handler's **rank** comes from its
measured cost per call, not from what it says about itself. A **route** is the order a stream's handlers see an
input in: by rank, cheapest first.

| Type | Fields (besides title) |
| --- | --- |
| `stream` | description, source (where inputs come from), answers (`final`: the first answer ends the climb; `advisory`: answers are recorded and the input still goes to the top), outcome (how one is known) |
| `input` | stream, key, payload, arrived_at, status (`open`, `resolved`, `dropped`), outcome (value, by, at), resolved_by |
| `handler` | stream, kind (`script`, `hook`, `rule`, `model`, `session`, `person`), entry (the implementation's registered name), component (its part on a map, if any), measured cost per call, rank, calls, answers, escalations, refusals, scored, correct |
| `route` | stream, ladder (handler slugs, cheapest first), answers, basis |
| `call` | stream, input, handler, kind (`answer`, `escalate`, `waiting`, `dropped`, `refused`), value, confidence, reason, escalate_to, cost (seconds, usd, person), at, correct |

Relations: `call handledBy handler`, `call handles input`, `input on stream`, `handler subscribesTo stream`,
`route orders stream`.

## The contract (`ladder.py`)

```
handler(input, ask) -> Answer(value, confidence in [0, 1])
                     | Escalate(reason, to=None)
                     | Waiting(reason)          # a person: no answer yet
                     | Dropped(reason)          # the input went away before anyone answered
```

The runner (`ladder.Runner`) calls handlers in route order and records each call. It refuses a call, recorded as
`refused` with what was wrong, when:
- an answer has no confidence, or one outside [0, 1]
- an escalation has no reason
- a handler returns anything else
- a handler is called around the runner: one handler calling another directly instead of through `ask`, which
  records the nested call

A refused call counts as an escalation, and the input goes on up.

**Cost is measured by the runner, not reported.** For a synchronous handler, the runner times the call itself.
For a person, the cost is one person's attention plus the time from the input arriving to its decision, taken from
Workbench's own timestamps. Money (`usd`) stays 0 until model calls go through a gateway that counts them.

**Rank** orders all handlers by mean cost per call: a person's attention first, then money, then seconds. That
makes every person dearer than every model, and every model that costs money dearer than every free one. A
handler with no calls yet takes its kind's prior (script and rule cheapest, person dearest) until measured, and
is marked unmeasured.

## Sources

- **`decisions`**: Workbench's review lane. Each decision a given extractor raised (`raised_by`, `kind`) is an
  input, keyed by its key. The outcome is its status once a person (anyone other than the raiser) decides it, or
  `withdrawn` when the raiser drops it. Replays in time order.
- **`jsonl`**: a file of calls already made outside the runner (a hook that records its own runs). Each line is
  `{stream, handler, input, started, seconds, exit, note}`. Exit 0 is an answer with confidence 1. Anything else
  escalates, with the exit code as the reason.

## Built-in handlers

- **`precedent`** (kind rule): for a decision whose key is `a:b:c`, it looks at earlier decisions with the same
  key pattern (`a:b`) that a person decided before this input arrived. It answers with the most common one,
  with confidence = agreeing ÷ (precedents + 1). With no precedent, it escalates. It never looks at a decision
  made after the input it is answering, so a replay can't see its own future.
- **`review-lane`** (kind person): the review lane itself. Its answer is the person's decision. It waits while
  the decision is open, and drops when the raiser withdraws it.

Another plugin can add handlers with `@ladder.handler("name")`.

## Extractors

- **`handlers:declare`** (`--input file=PATH`): a YAML file of streams and their handlers, written as items.
- **`handlers:run`**: every stream's inputs, through its route. It records each call as a claim attributed to
  the handler (`handler:<slug>`), scores the calls against outcomes, and re-ranks the handlers. A replay changes
  nothing that hasn't changed.

## Check

`plugins/handlers/tests/test_ladder.py` (the contract, no database) and `test_handlers.py` (a replay in a
throwaway database: precedent answers, the review lane's outcomes, ranks from measured cost, claims attributed to
handlers, a refused handler).
