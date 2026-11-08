---
name: setup
description: Bring the substrate up on this machine and wire it - tools, clones, the service stack (kernel, Bifrost, Backstage, Prometheus), the gateway's providers (Claude, OpenRouter, local), Claude Code through the gateway, and the MCP connections. Use when the owner asks to set up, start, restart or repair the stack, or when scripts/check.sh fails.
---

# Set up the substrate

Work through the steps in order. Each ends with a check; do not start the next until it passes or the owner
has decided to skip it. Tell the owner, in a line, what each step did. Use the container engine set in
`.env` (`CONTAINER_ENGINE`, podman by default).

## 1. Host tools, clones and images

Run `scripts/bootstrap.sh`. On the host it needs only git, python3 (standard library), the engine and, for
`RUNTIME=compose`, its compose; everything else is built in containers (S-19). It clones kernel and Morphogen
into `repos/`, builds every image (`scripts/build.sh`: kernel, the tools image, Backstage in two stages) and
starts the `substrate-tools` container that `bin/` runs in.

- A missing host tool: tell the owner which and how to install it for their OS; look up the current
  instructions rather than recalling them. Do not install Python packages, Node, uv or gitleaks on the host:
  they are in the images.
- With Podman, `podman compose` needs a provider: `docker-compose` (preferred) or `podman-compose`. On macOS,
  `podman machine` must be running; the tools container uses host networking, which is untested there.
- The first Backstage build takes several minutes. When it writes `services/backstage/yarn.lock`, commit it.
  Record the digest of `docker.io/library/node:24-trixie-slim` it pulled (`<engine> image inspect docker.io/library/node:24-trixie-slim`) in
  `services/backstage/Containerfile` as `docker.io/library/node:24-trixie-slim@sha256:...`, so later builds use the same base.

**Check:** bootstrap ends with "Done"; `bin/kk --help` and `bin/gitleaks version` answer; `git -C repos/kernel
status` and `git -C repos/morphogen status` work.

## 2. Settings

If `.env` does not exist, `scripts/up.sh` creates it from `.env.example` and generates the secrets. Before
the first run, ask the owner for what only they can give, one question, all at once:

- `RUNTIME`: compose (default; Linux or macOS) or nomad (Linux; the chosen control plane, S-17). Recommend
  compose for the very first run and nomad once that passes, so a failure has one new cause at a time;
- `CONTAINER_ENGINE`: podman (their default) or docker;
- `SECRETS`: env (secrets in `.env`, the default) or openbao (OpenBao on 127.0.0.1:8200, S-31). Recommend env
  for the very first run, then `SECRETS=openbao` and `scripts/secrets.sh migrate` once `scripts/check.sh`
  passes, so a failure has one new cause at a time;
- `ANTHROPIC_API_KEY`: leave empty to use their Claude subscription through the gateway (recommended for
  Claude Code), or a key for API billing;
- `OPENROUTER_API_KEY`: for OpenRouter models;
- a local model server: Ollama at `http://host.docker.internal:11434` by default; `OLLAMA_ENABLED=false` if
  there is none; another URL if it runs elsewhere;
- ports, if 5432, 8080, 8090, 7007 or 9090 are taken (8100, the console, stays inside the stack).

Write their answers into `.env` (copy `.env.example` first if needed). Never echo a key back.

**Check:** `.env` exists with mode 600.

## 3. The stack

Run `scripts/up.sh`. It renders the gateway config, builds the kernel image and (first time, several
minutes) the Backstage image, starts every service, waits for each, then connects this repository to
kernel with `kk up --no-stack` (owner and agent logins in `~/.config/knowledge-kernel`, `.mcp.json`,
kernel's skill and hooks).

If a service does not come up, read its logs (`scripts/logs.sh <service>`), find the cause, fix it in this repository, and run
`scripts/up.sh` again. Known places to look:

- **bifrost** refuses its config: read the error; the format is in Bifrost's docs for v2.3.2
  (`quickstart/gateway/provider-configuration.mdx`). If an `anthropic` provider with no keys is the
  problem, change `scripts/render_bifrost.py`, not the rendered file.
- **backstage** build fails: read the build output (`scripts/build.sh backstage`); it runs in
  `services/backstage/Containerfile`, so fix it there. A dependency that needs a system library goes into the
  build stage's `apt-get install` line.
- **tools** container: `scripts/tools.sh status`; `bin/kk` says when it is not running. If a hook or the kernel
  MCP server fails in Claude Code, run the same command through `bin/` by hand to see its error.
- **kernel** with Podman: kernel's own `kk up` calls `docker`; substrate avoids it by starting the stack
  itself. The fix upstream is `upstream/kernel/0001-*.patch` (the `upstream` skill).
- **Nomad runtime**: the agent log is `.state/nomad/agent.log`; `nomad job status substrate` and
  `scripts/logs.sh <task>` show each task. With Podman, the driver needs Podman's API socket
  (`systemctl --user enable --now podman.socket`) and `nomad node status -self -verbose` should list
  `driver.podman` as healthy; if it does not load on Nomad 2.0.7, read the driver's release notes for the
  supported Nomad versions and pin a driver that matches (record it in `DECISIONS.md`). Rootless Podman
  cannot bind ports below 1024, which is why every port here is above it.

- **db**: kernel's Postgres image carries pgvector, pg_cron, pgmq and pgGraph (kernel D-94). If
  `scripts/bus.sh` says pgmq is not in the image, `repos/kernel` predates it: pull it, `scripts/build.sh db`,
  and restart the db service.
- **caddy** / **console**: `scripts/logs.sh caddy` and `scripts/logs.sh console`. The console runs in kernel's
  image as `nobody` and reads this checkout read-only; a permission error there means a file in the checkout is
  not world-readable.

- **secrets** with `SECRETS=openbao`: `scripts/secrets.sh status`; the server's log is
  `<engine> logs substrate-openbao`. Its unseal key and the scripts' password are in `.state/openbao/keys`
  (mode 600): back them up with `.state/openbao/data`, or the secrets are gone. To go back to `.env`, set
  `SECRETS=env` and write each value back with `scripts/secrets.sh put` (reading it first under openbao).
- **otel-collector**: `scripts/logs.sh otel-collector`. It needs `.state/otel` writable (up.sh makes it so). Claude
  Code's telemetry is switched on by `scripts/up.sh` for the connected project (`scripts/telemetry.py status`; off
  with `scripts/telemetry.py off`), from the next session. Backstage loads OpenTelemetry through NODE_OPTIONS: if
  it fails to start with a "Cannot find module @opentelemetry" error, its image predates the dependency, so run
  `scripts/build.sh backstage`. Bifrost reads its otel plugin from the config it was first seeded with; on an
  existing Bifrost data volume, add the plugin in its dashboard or start from a fresh volume.

**Check:** `scripts/check.sh` shows ok for kernel, gateway, map, prometheus, the console, the bus and the
OpenTelemetry collector. The console's Map (http://127.0.0.1:8080/console/#map) shows the parts running. Tell the
owner the kernel sign-in that `kk up` printed (name `owner`, the password it shows): it opens both kernel's UI
(http://127.0.0.1:8080/ui/) and the console (http://127.0.0.1:8080/console/). Ask them to sign in to the
console once and say what they see.

## 4. The gateway's providers

Open http://127.0.0.1:8090/ (BIFROST_PORT) with the owner. The rendered config seeded: Anthropic (key or
subscription pass-through), OpenRouter if a key was given, Ollama if enabled, and one virtual key
`substrate` allowed on all of them, with auth enforced on inference.

Prove each provider with one small request through the gateway, using the virtual key from `.env` (read it
into a shell variable; do not print it):

- Anthropic, API-key mode: `POST /anthropic/v1/messages` with `x-bf-vk` or `Authorization: Bearer <vk>`.
  Subscription mode is proven in step 5 by Claude Code itself.
- OpenRouter: an OpenAI-compatible chat completion with model `openrouter/<model>`; for tests use a `:free`
  model under 10B parameters (kernel's rule for evals; Oct 2026: `liquid/lfm-2.5-2.6b:free`).
- Ollama: `ollama/<a model the owner has pulled>` (`ollama list` on the host).

Look up the exact routes in Bifrost's docs before calling them. The dashboard is password-protected from the
first start (S-34): user `admin`, password `scripts/secrets.sh get BIFROST_ADMIN_PASSWORD`; `/metrics` is
whitelisted so Prometheus scrapes without it.

**Check:** each configured provider answered once; `scripts/check.sh` shows the gateway's metrics.

## 5. Claude Code through the gateway

Only after step 4. Run `scripts/gateway.py on` (subscription mode; `--mode api-key` if `ANTHROPIC_API_KEY`
is set and the owner prefers API billing). It writes `ANTHROPIC_BASE_URL` and the virtual-key header into
`.claude/settings.local.json`, keeping kernel's entries. It applies to the next session: ask the owner to
restart Claude Code in this folder, send one prompt, and confirm a new request appears in Bifrost's logs.
If the session cannot reach a model, they run `scripts/gateway.py off` from a terminal and restart.

Unset any `CLAUDE_CODE_USE_*` variable in their environment first: each sends Claude Code to a cloud
provider instead of the gateway.

**Check:** `scripts/gateway.py status` says routed; Bifrost logs show the session's requests;
`bifrost_cost_total` or token counters move.

## 6. MCP connections

- **kernel:** `kk up` wrote it into `.mcp.json`; the owner approves the `kernel` server when Claude Code asks.
  Check with one `recall` about this repository.
- **Backstage:** add it at local scope, reading the token from `.env` without printing it:
  `claude mcp add --transport http --scope local backstage http://127.0.0.1:7007/api/mcp-actions/v1 --header "Authorization: Bearer $BACKSTAGE_MCP_TOKEN"`.
  Confirm the flags with `claude mcp add --help` first. Check: list the catalog's components through it.
- **Morphogen:** the plugin, from GitHub so the judge is never the code being judged (it runs on the host,
  with uv, because Claude Code starts it; this is the one host tool beyond the basics, and only for judged runs):
  `/plugin marketplace add OpenReplicant/Morphogen`, then `/plugin install morphogen@morphogen`. Check:
  its `status` tool on this repository (`morphogen.yaml` reads `catalog-info.yaml`).

**Check:** `scripts/check.sh` passes; the owner has seen each of the three answer.

## Afterwards

If `docs/spec.md` is in place, this was step 0 of its build plan: when `scripts/check.sh` passes on compose,
mark it (`python3 scripts/spec.py set 0 done` once Nomad passes too, or `blocked` with `--waiting-on` saying
what Nomad needs) and continue with the build-out skill.

Record anything that differed from these steps (a flag that changed, a provider quirk) as a fix: in this
skill or the scripts when it is substrate's, upstream when it is kernel's or Morphogen's.
