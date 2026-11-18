---
name: setup
description: Bring the substrate up on this machine and wire it - the tools container, the stack (Postgres, the model gateway, Ollama) and its databases. Use when the owner asks to set up, start, restart or repair the stack, or when scripts/check.sh fails.
---

# Set up the substrate

Work through the steps in order. Each ends with a check; do not start the next until it passes or the owner
has decided to skip it. Tell the owner, in a line, what each step did. Use the container engine set in
`.env` (`CONTAINER_ENGINE`, podman by default).

The stack on the fresh tree (S-137) is Postgres (`deploy/postgres`), the model gateway (Bifrost) and Ollama,
plus the `substrate-tools` container. The store's schema, its API and UI arrive with `docs/plan.md` step 3b.

## 1. Host tools and images

Run `scripts/bootstrap.sh`. On the host it needs only git, python3 (standard library), the engine and its
compose; everything else is built in containers (S-19). Never install a package on the host for substrate: a
tool goes into a container.

- A missing host tool: tell the owner which and how to install it for their OS; look up the current
  instructions rather than recalling them.
- With Podman, `podman compose` needs a provider: `docker-compose` (preferred) or `podman-compose`.
- Podman with no `unqualified-search-registries` refuses short image names, so every image is named with its
  registry (S-34).

**Check:** bootstrap ends with "Done"; `bin/gitleaks version` answers.

## 2. Settings

If `.env` does not exist, `scripts/up.sh` creates it from `.env.example` and generates the secrets. Before
the first run, ask the owner the only things that are theirs, in one question: `CONTAINER_ENGINE` (podman, their
default, or docker) and, if 5432, 8090 or 11434 is taken, other ports. Never echo a secret back.

**Check:** `.env` exists with mode 600.

## 3. The stack

Run `scripts/up.sh`. It renders the gateway's config, starts the stack and the tools container, makes the
`substrate` database and the gateway's, and runs `scripts/check.sh`. If a service does not come up, read its
logs (`scripts/logs.sh db|gateway|ollama`), find the cause, fix it in this repository, and run `scripts/up.sh`
again. Known causes:

- **A refused Postgres password**: the volume (`substrate_db-data`) outlived the `.env` that made it. Keep the
  data: set the role to `.env`'s value over the container's socket, never printing it (`podman exec -i
  substrate-db-1 psql -U postgres` with `\set pw '…'` and `alter role postgres password :'pw'` on stdin), then
  run `scripts/up.sh` again; it resets the gateway's roles itself.
- **The gateway answers 400 to every call**: it knows no provider. With only local models, `.env` needs
  `OLLAMA_URL=http://ollama:11434`.

**Check:** `scripts/check.sh` passes and says only the core runs.

## Afterwards

Continue with `docs/plan.md`. Record anything that differed from these steps as a fix in this skill or the
scripts.
