---
name: setup
description: Bring the substrate up on this machine and wire it - the tools container, the stack (Postgres, PostgREST, the Workbench server, Caddy), Workbench's schema and substrate's plugin, the owner's account, and Claude Code's MCP connections (Workbench, Morphogen). Use when the owner asks to set up, start, restart or repair the stack, or when scripts/check.sh fails.
---

# Set up the substrate

Work through the steps in order. Each ends with a check; do not start the next until it passes or the owner
has decided to skip it. Tell the owner, in a line, what each step did. Use the container engine set in
`.env` (`CONTAINER_ENGINE`, podman by default).

The stack is the core only (S-41, S-57): Postgres (`deploy/postgres`), PostgREST, the Workbench server and Caddy
at http://127.0.0.1:8080, plus the `substrate-tools` container. Anything else is an option on the
map, system `options`; each entry says how to bring it back. Do not set one up here unless a
build step needs it.

## 1. Host tools, clones and images

Run `scripts/bootstrap.sh`. On the host it needs only git, python3 (standard library), the engine and its
compose; everything else is built in containers (S-19). It clones Morphogen into
`repos/`, builds the images (`scripts/build.sh`: db, workbench, tools) and starts the `substrate-tools`
container that `bin/` runs in.

- A missing host tool: tell the owner which and how to install it for their OS; look up the current
  instructions rather than recalling them. Do not install Python packages, uv or gitleaks on the host: they are
  in the images.
- With Podman, `podman compose` needs a provider: `docker-compose` (preferred) or `podman-compose`. On macOS,
  `podman machine` must be running; the tools container uses host networking, which is untested there.
- Podman with no `unqualified-search-registries` refuses short image names, so every image is named with its
  registry (S-34).

**Check:** bootstrap ends with "Done"; `bin/gitleaks version` and `bin/morphogen --help` answer.

## 2. Settings

If `.env` does not exist, `scripts/up.sh` creates it from `.env.example` and generates the secrets. Before
the first run, ask the owner the only things that are theirs, in one question: `CONTAINER_ENGINE` (podman, their
default, or docker) and, if 5432 or 8080 is taken, other ports. Write the answers into `.env`. Never echo a
secret back.

**Check:** `.env` exists with mode 600.

## 3. The stack

Run `scripts/up.sh`. It builds the images, starts the stack, migrates Workbench's database, loads substrate's
plugin, runs its extractors (catalog, Claude Code's skills and hooks, Morphogen's verdicts, drift), adds the
`claude-code` agent's account, and wires this project's Claude Code (`scripts/harness.py`: Workbench's MCP server
in `.mcp.json`, with a headers helper that mints a fresh token per connection).

If a service does not come up, read its logs (`scripts/logs.sh <service>`: db, postgrest, workbench, caddy), find
the cause, fix it in this repository (or upstream, with the `upstream` skill, when it is Morphogen's), and run
`scripts/up.sh` again. Known places to look:

- **tools** container: `scripts/tools.sh status`. If a hook fails in Claude Code, run the same command by hand.
- **db**: the image carries pgvector, pg_cron, pgmq and pgGraph (`deploy/postgres/Dockerfile`). Its volume
  is `substrate_db-data`.
- **workbench**: `scripts/logs.sh workbench`; `http://127.0.0.1:8080/wb/api/health` says whether it relays events,
  takes jobs, and which plugins loaded (a plugin's error is shown there).

**Check:** `scripts/check.sh` passes and says only the core runs.

## 4. The owner's account and Claude Code

- **The owner** creates their own account; the password prints once, so they run it in their own terminal (not
  with `!`, which would put it in the chat): `scripts/workbench.sh user add NAME --role owner`. Then they sign in
  at http://127.0.0.1:8080/.
- **Workbench's MCP server** is in `.mcp.json` (`workbench`); Claude Code asks to approve it the first time.
  Check with one `search` or `list_types` call.
- **Morphogen:** the plugin, from GitHub so the judge is never the code being judged (it runs on the host, with
  uv, because Claude Code starts it; the one host tool beyond the basics, and only for judged runs):
  `/plugin marketplace add OpenReplicant/Morphogen`, then `/plugin install morphogen@morphogen`. Check: its
  `status` tool on this repository (`morphogen.yaml` reads `catalog-info.yaml`, the map's export).

**Check:** `scripts/check.sh` passes; the owner has signed in, and has seen Workbench's MCP and Morphogen answer.

## Afterwards

If `docs/spec.md` is in place, continue with the build-out skill once `scripts/check.sh` passes.

Record anything that differed from these steps (a flag that changed, a quirk) as a fix: in this skill or the
scripts when it is substrate's, upstream when it is Morphogen's.
