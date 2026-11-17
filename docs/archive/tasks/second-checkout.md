# Task: a second checkout can run beside the first

**Model:** Opus. **Needs:** `fresh-clone.md`. From `docs/readiness.md`, walk 1: findings 5 and 11, and its
"Not checked" list. Without this, a fresh-clone run cannot be tested on the owner's machine without stopping
the owner's stack.

## Scope

1. The compose project name, the front door's port and the tools container's name come from `.env`
   (`COMPOSE_PROJECT`, `FRONT_PORT`, `TOOLS_CONTAINER`; defaults as today: `substrate`, 8080,
   `substrate-tools`), read through `env_value` like `DB_VOLUME`. Every hard-coded `8080` and
   `substrate-<service>-1` in scripts, `observe.yaml`, `harness.py`, `judged.py` and `morphogen.local.yaml`'s
   example reads the setting.
2. Then the test the readiness walk could not do: clone the repository to a scratch directory, set a different
   project name, ports and volumes, and follow README and the setup skill to a passing `scripts/check.sh`,
   beside the owner's running stack. Record build and download times and every step that needed something not
   written down. Take it down and remove its volumes and images afterwards (ask the owner before removing
   anything that is not the scratch clone's own).

## Files to touch

`deploy/compose.yaml`, `scripts/lib.sh`, `scripts/tools.sh`, `scripts/up.sh`, `scripts/check.sh`,
`scripts/harness.py`, `scripts/judged.py`, `scripts/gateway.py` (addresses only), `observe.yaml`,
`.env.example`, the setup skill, `docs/readiness.md` (the measured results, under "Not checked"),
`DECISIONS.md` (one row).

## Leave alone

The owner's stack, volumes, `.env` and models: the scratch clone uses its own names for everything. The GPU:
the scratch stack runs Ollama on the CPU or skips model pulls, and says which. `repos/`.

## Done when

The scratch clone's `scripts/check.sh` passes while the owner's stack is up and its own check still passes;
the scratch stack is gone afterwards (`podman ps -a`, `podman volume ls` show nothing of it);
`docs/readiness.md` has the timings.
