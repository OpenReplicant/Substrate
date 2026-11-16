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
| `stream` | description, source (where inputs come from), episode (for an environment: its directory, max_steps, model, private fields), answers (`final`: the first answer ends the climb; `advisory`: answers are recorded and the input still goes to the top), outcome (how one is known) |
| `input` | stream, key, payload, arrived_at, status (`open`, `resolved`, `dropped`), outcome (value, by, at), resolved_by, final and episode (an episode's end state and its record) |
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

**Cost is measured, not reported.** For a synchronous handler, the runner times the call itself. For a person,
the cost is one person's attention plus the time from the input arriving to its decision, taken from Workbench's
own timestamps. For a model, it is the gateway's own record of the call (below).

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

- **`items`** (`type`): each live item of a content type someone saved (a question, a chore), oldest first. Its
  fields are the payload; it has no outcome of its own.

## Episodes (`episode.py`)

A stream can be an **environment** instead of a climb: each input starts an episode, and the route is asked at
every step, not once (the environment contract: an environment with Gymnasium's `reset(case, seed)` and
`step(action) -> (observation, reward, terminated, truncated, info)`, and `final()`, the state its outcome is read
from). `episode.run(env, case, order, entries)` is the step loop: the observation, the route asked with
`{"observation", "episode", "step", "actions"}` (the new claims, the steps before, the step's number, the action
kinds), the first answer's value as the action, `step`, until the episode ends: `terminated`, `truncated` (the
environment's limit or `max_steps`) or `escalated` (an escalation off the top of the route, or an action the
environment says hands the work up). The handler contract above does not change. `ask` (an action of every
environment) hands the step to another handler that exists, recorded as a call the asker made.

A judged run's driver and the `run` extractor call the same loop with the same handlers, so a benchmark and a live
input look alike to them. `episode.route(dir, agent, model, gateway)` builds the route an agent file describes:
cheapest first by kind (`select: cost-order`, the one selection built), a handler whose entry is a `.py` file in
the directory made by that file's `make(slug, cfg, gateway, dir)`.

A **package** directory (`environment.yaml`, `agent.yaml`, `environment.py`) is declared with
`handlers:declare --input packages=DIR,...`: the environment becomes a stream (its starting sensor's source, and
`episode`: the directory, `max_steps`, the environment's model, its `private` fields, which no handler is shown),
each handler in the agent file a handler named `<environment>-<name>`. On `handlers:run`, each new input runs one
episode: what the environment read is kept as sources and, whole, on the input (`episode.readings`: url, date,
body hash, body gzip-compressed), with each step's observation (claims), action and handler (`episode.log`), how
it ended, and `final`. Every call is recorded and metered as above. A hand-off leaves the input open and raises a
`hand-off` decision in the review lane; an episode a gateway refusal ended is run again on the next run.

## Built-in handlers

- **`precedent`** (kind rule): for a decision whose key is `a:b:c`, it looks at earlier decisions with the same
  key pattern (`a:b`) that a person decided before this input arrived. It answers with the most common one,
  with confidence = agreeing ÷ (precedents + 1). With no precedent, it escalates. It never looks at a decision
  made after the input it is answering, so a replay can't see its own future.
- **`review-lane`** (kind person): the review lane itself. Its answer is the person's decision. It waits while
  the decision is open, and drops when the raiser withdraws it.

Another plugin can add handlers with `@ladder.handler("name")`.

## Model handlers

A handler with `kind: model` and `entry: model` is the built-in model handler, with its own settings in the
streams file: `model` (the gateway's name for it), `answers` (the labels it may give), `sure_at` (below this
confidence it escalates; default 0.8) and `max_tokens`. It shows the model the input's key, its payload and the
earlier decisions, never the outcome, and asks for one JSON object: `answer`, `confidence`, `reason`. It
escalates when the model is not sure, when no answer among `answers` can be read from the reply, or when the
gateway turns the call away (that last kind is made again on the next run: a provider's limit is not the
model's judgment).

**Every call goes through a gateway that keeps its own record**, and the record, not the handler, gives the cost:

- the gateway is an OpenAI-style endpoint (`gateway_url`); each handler calls it with its own key, derived as
  `"sk-bf-" + HMAC-SHA256(gateway_secret, "handler:<slug>")[:40]`, so the gateway can be configured with the
  same keys and none is stored;
- each call carries a call id in the `x-wb-call` header, which the gateway keeps with its record;
- after the run, the meter (`meter_url`, a read-only login to the gateway's `logs` table) reads each call's
  record: its money, its time and its tokens become the call's cost, and the call is marked `metered`;
- a call the gateway records under another handler's key is refused, and so is one it has no record of once
  `meter_grace_minutes` (default 15) have passed: it went around the gateway, or never reached it.

Settings: `WB_HANDLERS_GATEWAY_URL`, `WB_HANDLERS_GATEWAY_SECRET`, `WB_HANDLERS_METER_URL`,
`WB_HANDLERS_METER_GRACE_MINUTES`. Without a gateway, a model handler escalates, saying so.

A handler added to a stream later is asked on the inputs already seen, where its answer can still count (an
advisory stream, or an input still open).

## Extractors

- **`handlers:declare`** (`--input file=PATH`, and `--input packages=DIR,...`): a YAML file of streams and their
  handlers, and package directories, written as items. One run declares both: a stream it no longer declares is
  retracted.
- **`handlers:run`**: every stream's inputs, through its route. It records each call as a claim attributed to
  the handler (`handler:<slug>`), scores the calls against outcomes, and re-ranks the handlers. A replay changes
  nothing that hasn't changed.

## Check

`plugins/handlers/tests/test_ladder.py` (the contract, no database), `test_handlers.py` (a replay in a
throwaway database: precedent answers, the review lane's outcomes, ranks from measured cost, claims attributed to
handlers, a refused handler) and `test_models.py` (model handlers through a fake gateway that keeps its own log:
cost from the gateway's record, escalations, a call the gateway never saw or saw under another key refused,
retries, a handler that joins later), and `test_episodes.py` (the step loop on a toy environment; a toy package
declared, saved items each running an episode, every step's call metered, a hand-off in the review lane, nothing
run twice, a refused episode run again).
