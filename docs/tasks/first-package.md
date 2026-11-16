# Task: the first package, end to end: `lookups`, one model, tools as actions

**Model:** Opus to build; Sonnet or Haiku for lookups and case writing. **Needs:** nothing. **First** (S-103).
Read `docs/contracts/environment.md`, `docs/tasks/starter-agent.md` (the parts table, the recording fetch,
"What a finished task is"), `scripts/trials/starter-agent/run.py`, `plugins/handlers/ladder.py`.

One package built whole, with the smallest form of everything it needs. Nothing general is built ahead of it:
what a second package would share is pulled out when the second one exists (`later-packaging.md`).

## Why lookups

The work repeats: "what licence is X under", "when was X last released", "does X have Y" are the same few
steps every time, so there is something to turn into a routine (`routines.md`). The answer is a registry
field at a recorded date, so a script scores it against an answer the agent never sees.

## Scope

1. **`packages/lookups/`** as the contract's file table: `environment.yaml`, `agent.yaml` with one model
   handler (Granite 4.0 Micro, held fixed, S-100), `environment.py`, `driver.py`, `score.py`, `cases/dev.jsonl`.
2. **Sensors and actions.** A question saved as an item starts an episode. Actions: search a registry, fetch
   a page, answer, hand off. The registries come from the map's `sources` system. A tool call is an action
   and its result the next observation; every fetch is recorded (URL, date, body hash, body) and a judged run
   replays the record with no network.
3. **The step loop, smallest form**: observation, the route asked at this step, action, `step`, until the
   episode ends. One function, called by the live path and by `driver.py`. It lives in the handlers plugin
   (general: nothing in it names a package). `ladder.py`'s handler contract does not change.
4. **Observations as claims**: the question and each tool result as claims; the model is shown them as text.
5. **The context log** (`context: append-only`), with what is dropped when the model's window fills stated
   in the same place. Read the gateway's and Ollama's current docs on prompt caching first (rule 1); print the
   meter's cached-token count for a multi-step episode.
6. **Cases.** `dev`: forty or more questions in a few repeating shapes, harder than the trial's (every model
   was at the ceiling there), with outcomes. Held-out: written and recorded by the operator outside the
   repository. Outcome metric: the share of answers equal to the recorded field; floors stated.
7. **One start.** `PACKAGES=lookups` in `.env`; `scripts/up.sh` declares that package. No script per mode:
   asking is saving a question (the shell, or MCP).

## Files to touch

`packages/lookups/` (new), `packages/README.md` (new, short), `plugins/handlers/` (the step loop, the saved-items
source, tests, README), `scripts/up.sh`, `.env.example`, `scripts/contract.sh` (the `environment` interface),
`morphogen.yaml` (a cell whose `change` is `packages/lookups/agent.yaml`, `handlers/` and `notes/`),
`CLAUDE.md` (commands), the map (rule 8), `DECISIONS.md`. Remove the stale `environments/` directory.

## Leave alone

`workbench/` core, `repos/`, the root `streams.yaml` and its three streams. `propose_handler`, other `select`
fillers, `state.yaml`, a general package loader: not this task.

## Done when

The owner saves a question and gets an answer or a hand-off, every call visible and counted at the gateway;
the contract test's checks pass on `dev` with no model; the driver runs the `dev` cases with the one model
handler and the score is between the floors and 1; `scripts/test.sh` and `scripts/check.sh` pass.
