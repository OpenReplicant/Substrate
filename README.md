# Substrate

A business, or any system, that keeps a cited model of itself, notices when practice drifts from intent,
and improves only on evidence it cannot fake.

Substrate assembles projects that each do one part, and adds the glue between them:

| Part | Project | Does |
| --- | --- | --- |
| World model | [kernel](https://github.com/OpenReplicant/kernel), cloned to `repos/kernel` | every claim in one Postgres: attributed, quoted, belief-scored, scoped, bitemporal; encoders, verifiers, recall, the review lane, the MAPE-K loop |
| Judge | [Morphogen](https://github.com/OpenReplicant/Morphogen), cloned to `repos/morphogen` | a change lands only with a verdict the changer cannot reach: rules from the base, outside measurement, held-out cases |
| Harness | Claude Code | the cognitive cycle, the builder, the mapper's hands |
| Gateway | [Bifrost](https://github.com/maximhq/bifrost) v2.3.2 | Claude (API key or your subscription), OpenRouter and local models behind one virtual key; every call measured outside the agent |
| Map | [Backstage](https://backstage.io) (`services/backstage`) | the catalog people browse, and an MCP endpoint agents query |
| Telemetry | Prometheus v3.15.0 | the gateway's tokens, cost and errors, for kernel to record as observations |
| Control plane | [Nomad](https://developer.hashicorp.com/nomad) 2.0.7, or compose | runs every service; one scheduler for containers, processes and clusters (`RUNTIME` in `.env`, S-16, S-17) |

Read as a mind, these are the Common Model of Cognition's modules: perception (briefings), declarative
memory (kernel), procedural memory (skills), motor (actuators), the cycle (Claude Code), learning
(Morphogen). Read as an organisation, they are the Viable System Model's five systems: operations
(builder, actuators), coordination (dispatcher), control (MAPE-K loop, Morphogen), intelligence (mapper),
policy (people, through clearance and review). Read as a product, they are a Foundry-shaped platform
whose every value can say where it came from.

`catalog-info.yaml` is the map: every part with the intent it serves and how it is filled, most of them
already built in kernel or Morphogen. Backstage shows it, Morphogen reads it as cells (`morphogen.yaml`).

## Start

Clone this repository, open Claude Code in it, and ask it to set up. The `setup` skill
(`.claude/skills/setup/SKILL.md`) walks through each step and checks it. By hand:

```sh
git clone https://github.com/OpenReplicant/Substrate substrate && cd substrate
scripts/bootstrap.sh          # tools, kernel and Morphogen cloned into repos/, kk and Morphogen installed
cp .env.example .env          # optional: set CONTAINER_ENGINE, provider keys, ports (up.sh does it otherwise)
scripts/up.sh                 # every service, then kernel connected to this repository
scripts/check.sh
scripts/gateway.py on         # Claude Code through the gateway, from the next session
```

On the host it needs only git, python3 (the scripts use its standard library), Podman (default) or Docker, and
Claude Code. Everything else is built and run in containers (S-19): kernel, gitleaks, uv and Morphogen in the
`substrate-tools` container, which the commands in `bin/` (`bin/kk`, `bin/morphogen`, kernel's MCP server and
hooks) run inside; Backstage in a two-stage container build.

## Runtimes

`RUNTIME` in `.env` picks what runs the services; every script works the same either way (S-16).

| `RUNTIME` | Runs on | Needs | Notes |
| --- | --- | --- | --- |
| `compose` (default) | Linux, macOS | `podman compose` or `docker compose` | kernel's own compose project plus `deploy/compose.yaml` |
| `nomad` | Linux | nothing more: `scripts/bootstrap.sh` installs Nomad 2.0.7 and the Podman driver, checksums checked | a single-node agent on 127.0.0.1 runs one job (`deploy/nomad/`); secrets in Nomad Variables; Prometheus finds services through Nomad. Licence: BUSL-1.1 (S-18) |

`CONTAINER_ENGINE` (podman or docker) is compose's engine or Nomad's task driver. Compose stays the default
until the Nomad runtime passes `scripts/check.sh` on a real machine; then it becomes the default (S-17).

| Service | Address (localhost only) |
| --- | --- |
| kernel UI and MCP | http://127.0.0.1:8080/ui/ (sign-in printed by `scripts/up.sh`) |
| model gateway | http://127.0.0.1:8090/ (Claude Code: `/anthropic`) |
| Backstage | http://127.0.0.1:7007/ (MCP: `/api/mcp-actions/v1`) |
| Prometheus | http://127.0.0.1:9090/ |

## Layout

```
CLAUDE.md                 instructions for the agent working here
DECISIONS.md              the defaults and why (S-01...), open questions
catalog-info.yaml         the map, as a Backstage catalog
morphogen.yaml            the map as Morphogen cells
repos.yaml                the upstream projects and the commits last checked
deploy/                   compose overlay on kernel's stack; nomad/ (agent and job); Prometheus config; observer queries
services/backstage/       the Backstage app (create-app 0.9.3) and substrate's config for it
modules/                  the glue, as kernel modules: briefs first
scripts/                  bootstrap, build, tools, up, down, logs, check, gateway, render_bifrost, point_harness, install_hashicorp
bin/                      kk, morphogen, gitleaks, kernel-mcp and its hooks: each runs inside the tools container
deploy/tools/             the tools image (kernel's image plus git and uv)
scripts/runtime/          one file per runtime: compose.sh, nomad.sh (rt_up, rt_down, rt_status, rt_logs)
upstream/                 fixes prepared for kernel or Morphogen, not yet opened as PRs
.claude/skills/           setup, upstream
repos/                    kernel and Morphogen clones (gitignored; each its own git repository)
```

## Working upstream

Fixes found while running the substrate go to kernel or Morphogen by branch and pull request in
`repos/<repo>` (the `upstream` skill). The first one is ready: `upstream/kernel/0001-*.patch` lets kernel's
`kk up` run on Podman.

## What to build next

1. `encoder-backstage`: the substrate's own map into kernel, so kernel models the system it runs in.
2. `encoder-morphogen`: verdicts into kernel, so what was judged is cited beside what was observed.
3. Gateway metrics as observations (`deploy/observer/`), so model cost is a claim.

Together they make the first distribution (S-10): the system minding itself.

## Licence

Apache-2.0, as kernel and Morphogen. `services/backstage` is generated from Backstage's template (Apache-2.0).
