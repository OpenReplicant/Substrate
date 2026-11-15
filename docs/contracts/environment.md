# Contract: the environment

Between an **environment** (one kind of work: its world, its cases, its outcome measure), the **agent** under
test (a candidate architecture), and **Morphogen** (which runs both and decides). It is new: nothing in code
has this interface yet. It starts from `plugins/handlers/ladder.py` (the handler contract), `bench/run.py` and
`bench/score.py` (the one judged workload), spec section 10 ("Environments: streams that act", S-80) and
`docs/direction.md` ("What research is aimed at").

The point of the contract: a benchmark and a live deployment of the same work look alike to the agent, and the
agent can never reach what scores it.

## Three parts, three custodies

| Part | Holds | Who may change it |
| --- | --- | --- |
| **World** | the state the work acts on (tickets, a database, documents), `reset` and `step`, the action gate | people; outside every cell's `change` |
| **Agent** | everything that turns an observation into an action: handlers, their route, prompts, knowledge files, recall | candidates; this is where cells are cut |
| **Scorer** | the outcome measure, run from the base outside the candidate, on held-out answers | people; the judge's custody |

## The world: reset and step

Gymnasium's interface (MIT), unchanged, so existing benchmarks wrap without translation:

```python
reset(case: dict, seed: int) -> observation
step(action: dict) -> (observation, reward, terminated, truncated, info)
```

- `case` is one line of the cases file: `{"id", ...}` with what the work starts from and **no outcome**.
- An **observation** is a dict of named fields, each a declared modality (`text`, `json`, `image`, ...). The
  environment declares an **encoder** per modality (how a field becomes what a handler is shown); `text` and
  `json` need none. Fields listed `private` are never shown to a handler below a person.
- An **action** is `{"kind": <one the environment declares>, ...}`. An action of an undeclared kind is
  refused and recorded; it does not end the episode.
- **The gate** is declared per action kind: `free` (the world applies it), `propose` (it is recorded and a
  person accepts, edits or ignores it), `deny`. A benchmark's actions are `free`; a live deployment starts at
  `propose`. Moving a kind from `propose` to `free` is a change of workflow (`workflow.md`), not of the agent.
- **`reward` is `None` on held-out cases.** Whatever the world can tell the agent mid-episode (a tool's
  result, a customer's reply) is observation. The score is not.
- `terminated`: the work ended (the agent closed it, or the world did). `truncated`: `max_steps` or the time
  limit ran out. Both count as an episode with an outcome.
- Same `case` and `seed` give the same first observation, and the same actions give the same episode, model
  calls aside.

## The agent: a route of handlers

Each step's observation is an **input** to the fallback learner's runner; the action is the answer's `value`.
So the agent's interface is already written (`ladder.py`):

```python
handler(observation, ask) -> Answer(value=action, confidence) | Escalate(reason, to=None) | Waiting | Dropped
```

A **plain-agent baseline** is a route of one model handler. A candidate architecture is a different route, or
a different component on the same route. An escalation that leaves the top of the route ends the episode as
`escalated`; the environment says what that scores (for support work: handed to a person, which is a cost, not
a failure). Several streams meet in the observation, never inside a handler. Every model call goes through the
gateway with the run's key; a call the meter did not see is refused (S-77, S-87).

## The model is held fixed

What is tested is the agent around the model (its route, prompts, knowledge, recall, tools), never the model.
A comparison names one model for the agent and one for the world, and both sides of every round use them. The
model's name is outside the candidate's `change`; swapping it is a different experiment with its own series.

Each environment declares its **minimum-viable model**: the cheapest model that scores clearly above the
environment's floor and below its ceiling on `dev` cases, taken from a published score where one exists and
confirmed here. Cheapest first, because the aim is a baseline and a difference, not a high score: a local
model that gets a third of the cases right shows a harness change as well as a large one does, at no cost. A
model at the floor is not viable (nothing can be made worse, so the judge cannot be checked), and neither is
one at the ceiling.

## The run and the scorer

The cell's `run` is the environment's **driver**: for each case in `MORPHOGEN_INPUTS/cases.jsonl` it resets the
world, steps until the episode ends, and prints one JSON line:

```json
{"id": "...", "end": "terminated|truncated|escalated", "steps": 7, "final": {...}, "actions": [...]}
```

`final` is the world's state that the outcome is read from (the ticket's fields, the rows changed, the
document produced), not the agent's account of it. The cell's `score` reads those lines on stdin and the
answers in `MORPHOGEN_PRIVATE`, and prints one JSON object of metrics. Each environment names:

- **one outcome metric** in [0, 1], `scored.<name>`, with its floor stated (what a do-nothing agent and a
  constant agent score), so a number is readable on its own, as `scored.balanced` states 0.5;
- **the cost metrics**: `metered.calls` and `metered.tokens`, from the meter;
- secondary metrics as wanted (`scored.escalated`, `scored.steps`), which may bound but never decide alone.

A line the scorer cannot read, a missing case and a duplicate id each score as the floor for that case.

## Cases: three sets, three places

| Set | Where | Read by |
| --- | --- | --- |
| `dev` | in the repository, with outcomes | anyone: building, contract tests, cheap screens |
| `search` | the operator's machine (`morphogen.local.yaml`: `search`) | probes and optimizers, through the judge only |
| `held-out` | the operator's machine (`private`, with `inputs` beside it) | the scorer in a verdict, nothing else |

The three never overlap. A benchmark's public test set counts as `dev` (models may have seen it); held-out
cases are ones the environment can make fresh, or a split the operator draws once and records by digest. A
held-out case's outcome never appears in another case's history, an observation, the Knowledge Kernel or
another environment.

## Declaration

`environments/<slug>/environment.yaml`, with `world.py`, `driver.py`, `score.py` and `cases/dev.jsonl` beside
it. The streams block is `streams.yaml`'s shape, so the handlers plugin reads it as it does now.

```yaml
environment: <slug>
work: support | back-office | coding
licence: <the benchmark's, and where it was read>
world: {entry: world.py, max_steps: 30, seconds: 300}
observation: {fields: {message: text, record: json}, private: [outcome]}
actions: {reply: free, update_record: free, refund: propose, hand_off: free}
model: {agent: ollama/<name>, world: ollama/<name>}     # held fixed; the minimum-viable model
outcome: {metric: scored.resolved, floor: {nothing: 0.0, constant: 0.0}, scorer: score.py}
cost: [metered.calls, metered.tokens]
budget: {calls_per_episode: 12, cases_held_out: 60}     # the arithmetic of direction step 1
streams: {...}
```

## Check (the contract test, `scripts/contract.sh environment <slug>`)

On `dev` cases only, with no model:

1. `reset` twice with one case and seed gives equal observations; `step` after the end raises.
2. No observation carries a `private` field or any key of the dev outcomes.
3. A do-nothing agent and a constant agent score the declared floors; replaying the dev answers scores 1.
4. An action of an undeclared kind, and a `deny` kind, are refused and recorded.
5. A driver line with a made-up `reward` or `score` key, or a `final` the actions could not have produced,
   does not raise the score (the forged-transcript case below).

## Open

- **A forged `final`.** The driver runs in the candidate's process, so a candidate could print a `final` the
  world never reached. The driver and world are outside `change`, which Morphogen enforces on files, but not on
  what a changed file does at run time. First defence: the scorer replays `actions` against a fresh world from
  the base and scores the state it reaches itself, ignoring `final` when they differ. That needs worlds to be
  replayable without model calls, which the determinism rule above gives for simulated worlds. A world that cannot
  be replayed is served outside the run (Morphogen's `services`) and keeps its own log; whether the scorer can
  read a service's log is not checked yet, and is a question for Morphogen before such a world is used. The
  cheat goes into the red team first (Morphogen's rule).
- **Encoders** beyond `text` and `json` are named here and built when an environment needs one.
- **Simulated users.** Support benchmarks often play the customer with a model. Its calls are the world's cost,
  not the agent's: they go through the gateway under a second key so `metered.*` counts the agent alone, and
  the budget arithmetic counts both.
