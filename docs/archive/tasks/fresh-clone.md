# Task: a fresh clone comes up without the owner's machine

**Model:** Opus. **Needs:** nothing. From `docs/readiness.md`, walk 1: findings 1, 2, 3, 4, 8, 9, 13, 14, 15.
These are the ones that stop or slow a newcomer before the stack is up.

## Scope

1. **No PyYAML on the host** (1): `up.sh` runs `gateway.py render` through `bin/in-tools`, as it runs `init`;
   `check.sh` parses YAML inside the tools container. The host keeps to Python's standard library, as README says.
2. **Ollama has a route by default** (3): `.env.example` sets `OLLAMA_URL=http://ollama:11434` (S-83's value),
   with the host address as the commented alternative.
3. **Models are pulled** (4): one place (extend `recall.sh`'s pull, or a small `models.sh` that `up.sh` calls)
   pulls every `ollama/` model named in `streams.yaml` and the embedding model, once, saying the size first.
4. **The engine is asked first** (8): the setup skill asks `CONTAINER_ENGINE` before bootstrap, and documents
   `CONTAINER_ENGINE=docker scripts/bootstrap.sh`.
5. **Host tools are checked** (9, 14): bootstrap requires `curl`; it reports whether `uv` is there and says it
   is needed only for judged runs. README lists both, and Podman as the judged runs' sandbox.
6. **Architecture** (2): the tools image picks gitleaks by `TARGETARCH`. If the other pinned images have no
   arm64 build, say "x86_64 only" in README instead and stop there.
7. **The map check does not hang on the build plan** (13): close `check.sh`'s `if [ -f docs/build.yaml ]`
   after the plan's own line.
8. **An example for judged runs** (15): `morphogen.local.yaml.example` with every key and empty values.

## Files to touch

`scripts/up.sh`, `scripts/check.sh`, `scripts/bootstrap.sh`, `scripts/recall.sh` (or a new `scripts/models.sh`),
`.env.example`, `deploy/tools/Containerfile`, `.claude/skills/setup/SKILL.md`, `README.md` (the host
requirements paragraph only), `morphogen.local.yaml.example` (new), `DECISIONS.md` (one row), `CLAUDE.md`'s
command list if a script is added.

## Leave alone

The owner's `.env` and `morphogen.local.yaml`. Port 8080 and the compose project name (`second-checkout.md`).
Wording about the paused plan (`first-read-docs.md`). `scripts/gateway.py`'s meter. `repos/`.

## Done when

On this machine: `scripts/up.sh` and `scripts/check.sh` pass with PyYAML hidden from the host's python
(`python3 -S -c "import yaml"` failing is not enough: run them with a `PYTHONPATH` that shadows it, and say
how); `scripts/test.sh` passes. Each fix cites its finding in the commit message. What still needs a real fresh
machine is listed for `second-checkout.md`.
