# Later: what is pulled out when a second package exists

**Waiting** (S-103): none of this is built until `first-package.md` is done and a second package needs it.
It was written as the first task under S-102; the scope below stands, the order does not.


## Scope

1. **One start.** No script per mode. `scripts/up.sh` reads `PACKAGES` from `.env` (`PACKAGES=substrate,papers`;
   empty means none) and for each `packages/<slug>/` loads its `plugin/` if it has one and declares its
   sensors, handlers and route through the handlers plugin.
2. **Substrate's own streams become a package.** The root `streams.yaml` moves to `packages/substrate/`
   (`environment.yaml` for the three streams' sensors and outcomes, `agent.yaml` for their handlers), with the
   same behaviour. `scripts/streams.sh` reads packages; it is not a second way to start.
3. **A sensor source for saved items** in the handlers plugin (`source: {kind: items, type: ...}`): an item
   someone saved (a person in the shell, an agent through MCP, an extractor) is a reading. General: nothing in
   it names a package.
4. **Sharing.** A package directory is self-contained (the contract's file table) with a `state.yaml` of the
   verdicts its agent passed. Copying it into another checkout and naming it in `PACKAGES` is the whole
   install. Held-out cases are never part of it.
5. **A sample package** (`packages/sample/`) with one script handler and no model, used by the test.

## Files to touch

`scripts/up.sh`, `scripts/streams.sh`, `.env.example`, `plugins/handlers/` (the items source, reading two
files, test, README), `packages/README.md` (new: how to enable, add and share one), `packages/substrate/`,
`packages/sample/`, `morphogen.yaml` and `scripts/` where they name `streams.yaml`, `CLAUDE.md` (commands),
the map (rule 8), `DECISIONS.md`. The empty `environments/` directory goes.

## Leave alone

`workbench/` core, `repos/`, `ladder.py`'s handler contract, the existing three streams' behaviour. The
step loop is `first-package.md`; routines and `propose_handler` are `routines.md`.

## Done when

With `PACKAGES=substrate` the stack behaves as today; with `sample` added, `scripts/up.sh` declares it, an
input saved as an item goes up its route to the script handler, and no new script was needed to run it;
`scripts/test.sh` and `scripts/check.sh` pass.
