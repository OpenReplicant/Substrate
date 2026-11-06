# Substrate

A business, or any system, that keeps a cited model of itself, notices when practice drifts from intent,
and improves only on evidence it cannot fake.

Substrate assembles projects that each do one part, and adds the glue between them (S-01):

| Part | Project | Does |
| --- | --- | --- |
| World model | [kernel](https://github.com/OpenReplicant/kernel) (`vendor/kernel`) | every claim in one Postgres: attributed, quoted, belief-scored, scoped, bitemporal; encoders, verifiers, recall, the review lane, the MAPE-K loop |
| Judge | [Morphogen](https://github.com/OpenReplicant/Morphogen) (`vendor/morphogen`) | a change lands only with a verdict the changer cannot reach: rules from the base, outside measurement, held-out cases |
| Harness | Claude Code | the cognitive cycle, the builder, the mapper's hands |
| Gateway | [Bifrost](https://github.com/maximhq/bifrost) v2.3.2 | every model call routed and measured outside the agent |
| Telemetry | Prometheus v3.15.0 | the gateway's tokens, cost and errors, recorded by kernel as observations |

Read as a mind, these are the Common Model of Cognition's modules: perception (briefings), declarative
memory (kernel), procedural memory (skills), motor (actuators), the cycle (Claude Code), learning
(Morphogen). Read as an organisation, they are the Viable System Model's five systems: operations
(builder, actuators), coordination (dispatcher), control (MAPE-K loop, Morphogen), intelligence (mapper),
policy (people, through clearance and review). Read as a product, they are a Foundry-shaped platform
whose every value can say where it came from.

`catalog-info.yaml` is the map: 30 components, each with the intent it serves and how it is filled. 21 exist
already, 3 are adopted open source, 6 are to build. Morphogen reads it as cells (`morphogen.yaml`).

## Start

Needs Docker or Podman with compose, Python 3.12+, git, and Claude Code.

```sh
git clone --recurse-submodules <this repository> substrate && cd substrate
scripts/up.sh ~/code/my-project
```

That runs kernel's `kk up` on the project (its stack, logins, MCP, skill and hooks), then starts the gateway
and Prometheus beside it. Then wire Claude Code through the gateway and install Morphogen's plugin:
[harness/README.md](harness/README.md).

## Layout

```
DECISIONS.md        the defaults and why (S-01..S-10), open questions
catalog-info.yaml   the map, as a Backstage catalog
docs/catalog.html   the map as an interactive graph (open in a browser)
morphogen.yaml      the map as Morphogen cells
deploy/             compose overlay on kernel's stack (gateway, Prometheus), observer queries
harness/            Claude Code wiring: kernel, Morphogen, the gateway
modules/            the glue, as kernel modules: briefs first
scripts/up.sh       one command for one project
vendor/kernel       kernel at c23a982 (git submodule)
vendor/morphogen    Morphogen at 4f36687 (git submodule)
```

## What to build first

1. `encoder-backstage`: the substrate's own map into kernel, so kernel models the system it runs in.
2. `encoder-morphogen`: verdicts into kernel, so what was judged is cited beside what was observed.
3. Gateway metrics as observations (`deploy/observer/`), so cost is a claim.

Together they make the first distribution (S-10): the system minding itself. Then the resolver (with
kernel's M6-T9) and the dispatcher (on kernel's M6-T0).

## Rules

Kernel's and Morphogen's rules hold here: every claim attributed and quoted, nothing deleted, people hold
clearance, no method verifies its own output; red team first; pin exact versions and check licences
(permissive or LGPL libraries in the default stack); look up current docs before relying on a tool. Apache-2.0,
as both.
