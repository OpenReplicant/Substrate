---
name: setup
description: Bring the substrate up on this machine and wire it - tools, clones, kernel's stack (Postgres, kernel, its Caddy), the tools container, and the MCP connections to kernel and Morphogen. Use when the owner asks to set up, start, restart or repair the stack, or when scripts/check.sh fails.
---

# Set up the substrate

Work through the steps in order. Each ends with a check; do not start the next until it passes or the owner
has decided to skip it. Tell the owner, in a line, what each step did. Use the container engine set in
`.env` (`CONTAINER_ENGINE`, podman by default).

The stack is the core only (S-41): kernel's Postgres, kernel, kernel's Caddy at http://127.0.0.1:8080, and the
`substrate-tools` container. Anything else (a model gateway, metrics, traces, a catalog browser, a scheduler, a
secrets store, a bus, a console) is an option in `catalog-info.yaml`, system `options`; each entry says how to
bring it back. Do not set one up here unless a build step needs it.

## 1. Host tools, clones and images

Run `scripts/bootstrap.sh`. On the host it needs only git, python3 (standard library), the engine and its
compose; everything else is built in containers (S-19). It clones kernel and Morphogen into `repos/`, builds the
images (`scripts/build.sh`: kernel, kernel's Postgres, the tools image) and starts the `substrate-tools`
container that `bin/` runs in.

- A missing host tool: tell the owner which and how to install it for their OS; look up the current
  instructions rather than recalling them. Do not install Python packages, uv or gitleaks on the host: they are
  in the images.
- With Podman, `podman compose` needs a provider: `docker-compose` (preferred) or `podman-compose`. On macOS,
  `podman machine` must be running; the tools container uses host networking, which is untested there.
- Podman with no `unqualified-search-registries` refuses short image names, so every image is named with its
  registry (S-34), `CADDY_IMAGE` included.

**Check:** bootstrap ends with "Done"; `bin/kk --help` and `bin/gitleaks version` answer; `git -C repos/kernel
status` and `git -C repos/morphogen status` work.

## 2. Settings

If `.env` does not exist, `scripts/up.sh` creates it from `.env.example` and generates the secrets. Before
the first run, ask the owner the only things that are theirs, in one question: `CONTAINER_ENGINE` (podman, their
default, or docker) and, if 5432 or 8080 is taken, other ports. Write the answers into `.env`. Never echo a
secret back.

**Check:** `.env` exists with mode 600.

## 3. The stack

Run `scripts/up.sh`. It builds the images, starts kernel's stack, waits for kernel, then connects this
repository to kernel with `kk up --no-stack` (owner and agent logins in `~/.config/knowledge-kernel`,
`.mcp.json`, kernel's skill and hooks) and reads `catalog-info.yaml` into kernel (`scripts/map.sh`).

If a service does not come up, read its logs (`scripts/logs.sh <service>`: db, init, kernel, caddy), find the
cause, fix it in this repository (or upstream, with the `upstream` skill, when it is kernel's), and run
`scripts/up.sh` again. Known places to look:

- **tools** container: `scripts/tools.sh status`; `bin/kk` says when it is not running. If a hook or the kernel
  MCP server fails in Claude Code, run the same command through `bin/` by hand to see its error.
- **kernel** with Podman: kernel's own `kk up` calls `docker`; substrate avoids it by starting the stack itself
  and calling `kk up --no-stack` (kernel D-96).
- **db**: kernel's Postgres image carries pgvector, pg_cron, pgmq and pgGraph (kernel D-94). If an extension is
  missing, `repos/kernel` predates it: pull it, `scripts/build.sh db`, and restart the db service.

**Check:** `scripts/check.sh` passes, and says only the core runs. Tell the owner the kernel sign-in that
`kk up` printed (name `owner`, the password it shows) for http://127.0.0.1:8080/ui/, and ask them to open the
review lane once.

## 4. MCP connections

- **kernel:** `kk up` wrote it into `.mcp.json`; the owner approves the `kernel` server when Claude Code asks.
  Check with one `recall` about this repository.
- **Morphogen:** the plugin, from GitHub so the judge is never the code being judged (it runs on the host,
  with uv, because Claude Code starts it; this is the one host tool beyond the basics, and only for judged runs):
  `/plugin marketplace add OpenReplicant/Morphogen`, then `/plugin install morphogen@morphogen`. Check:
  its `status` tool on this repository (`morphogen.yaml` reads `catalog-info.yaml`).

**Check:** `scripts/check.sh` passes; the owner has seen both answer.

## Afterwards

If `docs/spec.md` is in place, continue with the build-out skill once `scripts/check.sh` passes.

Record anything that differed from these steps (a flag that changed, a quirk) as a fix: in this skill or the
scripts when it is substrate's, upstream when it is kernel's or Morphogen's.
