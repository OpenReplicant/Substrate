# Task: an environment is one file that is started, adapted and shared

**Model:** the largest for the contract change, Opus to build. **Needs:** nothing. **First** (S-101). Read
`docs/contracts/environment.md`, `docs/tasks/starter-agent.md`, `plugins/handlers/README.md`.

## Scope

1. **Widen the contract** (`docs/contracts/environment.md`, "Declaration"): `environment.yaml` names everything
   one kind of work needs, each a component on the map: `streams`, `objects` (content types), `actions` and
   their gate, `parameters` (what may be tuned, with ranges), `handlers` and their route, `encoders` and
   `processors` (how an input becomes what a handler is shown, and how a result becomes items), `tools`
   (local code or a reached MCP server or command), `model` (held fixed), `cases`, `outcome`. Say which fields
   are required for an environment that only reads (no world to step) and which for one that acts.
2. **One start.** No script per mode. `scripts/up.sh` reads which environments are enabled (a setting in `.env`,
   `ENVIRONMENTS=papers,codebase`; empty means none) and declares each one's streams, types and handlers
   through the handlers plugin. Inputs arrive as items someone saved (a person in the shell, an agent through
   MCP, an extractor); what happens to an input follows the environment's file. `scripts/streams.sh` and the
   root `streams.yaml` become the `substrate` environment's file or are read beside it: say which, keep
   behaviour.
3. **A source kind for saved inputs** in the handlers plugin (general, nothing in it names an environment).
4. **Sharing.** An environment directory is self-contained: its file, its plugin code, its `dev` cases, its
   notes, and a `state.yaml` listing the verdicts its current components passed (cell, `seq`, `hash`,
   candidate commit). Copying the directory into another checkout and enabling it is the whole install. Held-out
   cases are never part of it.

## Files to touch

`docs/contracts/environment.md`, `scripts/up.sh`, `scripts/streams.sh`, `.env.example`, `plugins/handlers/`
(the source kind, test, README), `environments/README.md` (new: how to enable, add and share one),
`CLAUDE.md` (commands), the map (rule 8), `DECISIONS.md`.

## Leave alone

`workbench/` core, `repos/`, `plugins/handlers/ladder.py`'s contract, the existing three streams' behaviour.

## Done when

With `ENVIRONMENTS=` empty the stack behaves as today; with a small sample environment enabled, `scripts/up.sh`
declares it, an input saved as an item goes up its route, and no new script was needed to run it;
`scripts/test.sh` and `scripts/check.sh` pass.
