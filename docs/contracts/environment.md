# Contract: the environment, the agent and the package

Between an **environment** (what is sensed, what may be done, how the outcome is known), an **agent** (a
candidate architecture: whatever turns an observation into an action), and **Morphogen** (which runs both and
decides). A **package** is the directory that holds one environment and an agent configured for it, and is
what gets started and shared (S-102). It starts from `plugins/handlers/ladder.py` (the handler contract),
`bench/run.py` and `bench/score.py` (the one judged workload), spec section 10 and `docs/archive/direction.md`.

The words, each with one meaning (S-102 ends the overlap):

| Word | Means | Not |
| --- | --- | --- |
| environment | the agent's surroundings in the reinforcement-learning sense: sensors, actions and their gate, episodes, the outcome | the shared directory; a Workbench plugin; a mode of starting |
| agent | a policy from observation to action, built as a route of handlers. A model is one kind of handler and none is required | the model |
| package | `packages/<slug>/`: an environment, an agent, `dev` cases, plugin code they need, the verdicts passed | a running service |
| plugin | Workbench's unit of code (content types, extractors, views); a package may carry one | the package |

The point of the contract: a benchmark and a live deployment of the same work look alike to the agent, the
agent can be anything from one script to one model to a route that grows, and the agent can never reach what
scores it.

## Three parts, three custodies

| Part | Holds | Who may change it |
| --- | --- | --- |
| **Environment** | sensors and their encoders, the state the work acts on, `reset` and `step`, the action gate | people; outside every cell's `change` |
| **Agent** | everything that turns an observation into an action: handlers, how one is selected, prompts, notes, recall, parameters | candidates; this is where cells are cut |
| **Scorer** | the outcome measure, run from the base outside the candidate, on held-out answers | people; the judge's custody |

## The environment

### Sensors: what is observed

A **sensor** is anything the agent is subscribed to: a saved item, a file, a hook's run, a decision in the
moderation queue, a tool's result, a clock. (The handlers plugin's `stream` is a sensor's record in the
store.) Each **reading** is kept whole as an item. The sensor's **encoder** turns a reading into **claims**:
subject, property, value, source (the reading), time, and a confidence where the encoder is not certain. An
**observation** is the claims that are new since the agent's last step.

Claims, because both kinds of handler read them: a model is shown them as text, and a rule or script computes
on them, exactly or with their confidences. A sensor with no encoder gives one claim whose value is the
reading. Claims listed `private` are never shown to a handler below a person.

### Actions: what may be done

An **action** is `{"kind": <one the environment declares>, ...}`. A tool is an action kind: calling it is a
step, and its result comes back through a sensor as the next observation. So any handler can use a tool, not
only a model. An action of an undeclared kind is refused and recorded; it does not end the episode.

**The gate** is declared per action kind: `free` (the environment applies it), `propose` (it is recorded and
a person accepts, edits or ignores it), `deny`. A benchmark's actions are `free`; a live deployment starts at
`propose`. Moving a kind from `propose` to `free` is a change of workflow (`workflow.md`), not of the agent.

### Episodes: reset and step

Gymnasium's interface (MIT), unchanged, so existing benchmarks wrap without translation:

```python
reset(case: dict, seed: int) -> observation
step(action: dict) -> (observation, reward, terminated, truncated, info)
```

- Judged, an episode starts with `reset(case)`: `case` is one line of the cases file, `{"id", ...}` with what
  the work starts from and **no outcome**. Live, an episode starts when a reading arrives on a sensor the
  environment marks as starting one (a paper saved, a chore filed); the reading is the case. After that the
  two are the same loop.
- **`reward` is `None` on held-out cases.** Whatever the environment can tell the agent mid-episode (a tool's
  result, a reply) is observation. The score is not.
- `terminated`: the work ended (the agent closed it, or the environment did). `truncated`: `max_steps` or the
  time limit ran out. Both count as an episode with an outcome.
- Same `case` and `seed` give the same first observation, and the same actions give the same episode, model
  calls aside. A sensor that reads the outside (a fetch) records what it read, and a judged run replays the
  record, so base and candidate see the same surroundings.

## The agent

Each step's observation goes to the agent, and the action is its answer's `value`. The handler interface is
already written (`ladder.py`) and does not change:

```python
handler(observation, ask) -> Answer(value=action, confidence) | Escalate(reason, to=None) | Waiting | Dropped
```

The route is asked **at every step**, not once per input, so a cheap handler can take one step of an episode
and a dear one the next. An escalation that leaves the top of the route ends the episode as `escalated`; the
environment says what that scores.

### The default is one handler

`agent.yaml` in the package. The smallest agent is one handler:

```yaml
handlers:
  main: {kind: model, entry: model}     # or kind: script, rule, person
select: cost-order                      # the slot's default: today's route, cheapest first
context: append-only                    # how a model handler is shown the episode
parameters: {sure_at: {value: 0.8, range: [0.5, 0.95]}, max_steps: {value: 6, range: [2, 30]}}
```

With one model handler this is an ordinary model-only agent, and that is the baseline. With one script it is
an agent with no model at all. Nothing else is required.

### How it grows

Two actions belong to every environment, for the agent to change who does the work:

- **`ask`** (free): hand this step, or part of it, to another handler that exists. It is recorded as a call.
- **`propose_handler`** (always `propose`): a new handler, as code or a rule with the condition it answers
  under, written from what a dearer handler worked out. It is a change to the agent, so it is a candidate: it
  lands only on Morphogen's verdict and the workflow's approval, and until then it does not run live.

A lone model's instructions say it may do both. Whether it does, and whether what it builds is kept, is what
the experiments measure.

### What a model is shown

A model handler's context is the episode as an **append-only log**: the fixed part first (instructions, the
action kinds, notes), then each observation and action in order, including the steps other handlers took.
Bytes already sent are never rewritten, so the model's cache holds and a call pays for what is new. The meter's
cached-token count (`cell.md`, rule 3) shows whether it held. `context` is a slot; `append-only` is its default.

### The search space

Everything in the agent is a default meant to be beaten, at three levels (the owner's, S-102):

| Level | A change to | Example |
| --- | --- | --- |
| parameter | a value in `agent.yaml`, inside its declared range | `sure_at` from 0.8 to 0.7 |
| component | what fills a slot: a handler's code or prompt, an encoder, `select`, `context` | `select: cost-order` to one that picks by a learned condition |
| topology | which handlers exist and how they connect | a second handler added below the model |

A slot's other fillers are added when an experiment tries them, each recorded as a candidate in the catalog.
A cell's `change` names which of these a candidate may touch. `environment.yaml`, the sensors' encoders, the
driver and the scorer are outside every `change`.

Several sensors meet in the observation, never inside a handler. Every model call goes through the gateway
with the run's key; a call the meter did not see is refused (S-77, S-87).

## The model is held fixed

What is tested is the agent around the model (its handlers, selection, prompts, notes, recall), never the
model. A comparison names one model for the agent and one for the environment, and both sides of every round
use them. The model's name is outside the candidate's `change`; swapping it is a different experiment with its
own series.

Each environment declares its **minimum-viable model**: the cheapest model that scores clearly above the
environment's floor and below its ceiling on `dev` cases, taken from a published score where one exists and
confirmed here. Cheapest first, because the aim is a baseline and a difference, not a high score: a local
model that gets a third of the cases right shows a harness change as well as a large one does, at no cost. A
model at the floor is not viable (nothing can be made worse, so the judge cannot be checked), and neither is
one at the ceiling.

## The run and the scorer

The cell's `run` is the environment's **driver**: for each case in `MORPHOGEN_INPUTS/cases.jsonl` it resets the
environment, steps until the episode ends, and prints one JSON line:

```json
{"id": "...", "end": "terminated|truncated|escalated", "steps": 7, "final": {...}, "actions": [...]}
```

After the last case it prints one closing line, `{"episodes": N}`. Morphogen takes a run's last JSON line as
what the run reports about itself (`reported.*`, never deciding) and does not pass it to the scorer, so a driver
that ends on a case loses that case in every judged run (S-110).

`final` is the environment's state that the outcome is read from (the ticket's fields, the rows changed, the
claims recorded), not the agent's account of it. The cell's `score` reads those lines on stdin and the
answers in `MORPHOGEN_PRIVATE`, and prints one JSON object of metrics. Each environment names:

- **one outcome metric** in [0, 1], `scored.<name>`, with its floor stated (what a do-nothing agent and a
  constant agent score), so a number is readable on its own, as `scored.balanced` states 0.5;
- **the cost metrics**: the meter's factors (`cell.md`, rule 3);
- secondary metrics as wanted (`scored.escalated`, `scored.steps`), which may bound but never decide alone.

A line the scorer cannot read, a missing case and a duplicate id each score as the floor for that case.

The driver and the live runner call the same handlers. A package's handlers and encoders are therefore plain
functions that do not import the store: live, the handlers plugin wraps them; judged, the driver does.

## Cases: three sets, three places

| Set | Where | Read by |
| --- | --- | --- |
| `dev` | in the package, with outcomes | anyone: building, contract tests, cheap screens |
| `search` | the operator's machine (`morphogen.local.yaml`: `search`) | probes and optimizers, through the judge only |
| `held-out` | the operator's machine (`private`, with `inputs` beside it) | the scorer in a verdict, nothing else |

The three never overlap. A benchmark's public test set counts as `dev` (models may have seen it); held-out
cases are ones the environment can make fresh, or a split the operator draws once and records by digest. A
held-out case's outcome never appears in another case's history, an observation, the Knowledge Kernel or
another package.

## The package

`packages/<slug>/`: the whole install is copying the directory and naming it in `PACKAGES` (`.env`). The files
are the source; the items the store holds for a package are declared from them, as `streams.yaml`'s are now.

| File | Holds | Required |
| --- | --- | --- |
| `environment.yaml` | sensors and encoders, actions and gates, episodes, model, outcome | yes |
| `agent.yaml` | handlers, `select`, `context`, parameters | yes; one handler is enough |
| `environment.py` | `reset`, `step`, the encoders | when a sensor needs an encoder or an action has an effect to apply |
| `driver.py`, `score.py`, `cases/dev.jsonl` | the judged run | when the package is judged |
| `plugin/` | a Workbench plugin: the content types its claims use, views | when it adds types |
| `handlers/`, `notes/` | the agent's code and what it has learned | as the agent grows |
| `state.yaml` | the verdicts its current agent passed: cell, `seq`, `hash`, candidate commit | written, never edited by hand |

```yaml
environment: <slug>
work: research | support | back-office | coding
licence: <the benchmark's or data's, and where it was read>
sensors:
  inbox: {source: {kind: items, type: paper}, starts: true, encoder: paper_claims}
  fetched: {source: {kind: action, of: fetch}, records: true}
actions: {fetch: free, record_claim: free, hand_off: free}     # ask and propose_handler are always there
episode: {max_steps: 30, seconds: 300}
private: [outcome]
model: {agent: ollama/<name>, environment: null}               # held fixed; the minimum-viable model
outcome: {metric: scored.grounded, floor: {nothing: 0.0, constant: 0.0}, scorer: score.py}
budget: {calls_per_episode: 12, cases_held_out: 60}
```

Held-out cases are never in a package. Substrate's own streams are a package like any other
(`packages/substrate`, from today's root `streams.yaml`).

## Check (the contract test, `scripts/contract.sh environment <slug>`)

On `dev` cases only, with no model:

1. `reset` twice with one case and seed gives equal observations; `step` after the end raises.
2. No observation carries a `private` claim, or any claim about the case itself beyond what starts it (its
   outcome, its answer). A page the agent reads may contain the answer: that is the work.
3. A do-nothing agent and a constant agent score the declared floors; replaying the dev answers scores 1.
4. An action of an undeclared kind, and a `deny` kind, are refused and recorded.
5. A driver line with a made-up `reward` or `score` key, or a `final` the actions could not have produced,
   does not raise the score (the forged-transcript case below).
6. The package runs with `agent.yaml` cut to one script handler, and a `propose_handler` action changes
   nothing the next step can see.

## Open

- **A forged `final`.** The driver runs in the candidate's process, so a candidate could print a `final` the
  environment never reached. The driver and environment are outside `change`, which Morphogen enforces on
  files, but not on what a changed file does at run time. First defence: the scorer replays `actions` against
  a fresh environment from the base and scores the state it reaches itself, ignoring `final` when they differ.
  That needs environments to be replayable without model calls, which the determinism rule above gives for
  simulated ones. One that cannot be replayed is served outside the run (Morphogen's `services`) and keeps its
  own log; whether the scorer can read a service's log is not checked yet, and is a question for Morphogen
  before such an environment is used. The cheat goes into the red team first (Morphogen's rule).
- **Selection beyond cost order.** A handler that claims a step by a condition, or handlers that compete on a
  strength that rises with use and decays, are other fillers of `select`. So is choosing where an escalation
  goes by what each dearer handler (a model, an agent, a person) has been measured good at on that kind of
  task, instead of the next one up by cost. None is built; each is an experiment.
- **The context window.** An append-only log fills a small model's window on a long episode. What is dropped
  then is part of the `context` filler and must keep the sent prefix intact; `first-package.md` states it.
- **Which claims an encoder writes** for a given sensor is the encoder's, and a poor one hides what a rule
  could have used. Encoders are outside `change` now; whether they should become a governed component is open.
- **Encoders** for images and other modalities are named here and built when an environment needs one.
- **Simulated users.** Support benchmarks often play the customer with a model. Its calls are the
  environment's cost, not the agent's: they go through the gateway under a second key so `metered.*` counts
  the agent alone, and the budget arithmetic counts both.
