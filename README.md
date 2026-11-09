# Substrate

A self-modifying agent platform: an agent in charge of a system of components, and its own system is one of
them. It models each system as cited claims, acts on that model, and changes something (itself included) only
on evidence it cannot fake.

A component is anything that can be modified: a service, a library, a skill, a hook, a parameter, a prompt, a
vocabulary. The catalog uses Backstage's entity model because its kinds and types cover all of them, and
Morphogen judges anything named there as a cell.

- **Modelling itself** makes it autopoietic, and self is not a special case: it is one project among others.
- **Modelling other systems beside itself** makes it an engineer.
- **Adapting to model anything** that can be described as components makes it a generalist. That is the
  direction; managing systems of components is the scope.

## The loop

Observe a system (code, running services, people in interviews) and write what is learned as claims, each
attributed and quoting its evidence, typed by ontologies. The claims form a graph of the system, with an
intended half (what people declare) and an observed half (what encoders measure). Where the two disagree,
propose a response: a builder's change, an optimizer's tuning, a question to a person. The change lands only
with a verdict from a judge the changer cannot game, and the verdict becomes claims too.

Substrate's own architecture is in that graph, so changing itself is the same operation as changing anything
else.

It works like a scientist. Claims are hypotheses with a belief, a change is an experiment tested on cases the
changer has not seen, and negative results are kept. Choices come from catalogs rather than best guesses:
catalogs of components it can use, and catalogs of registries it can search (npm, PyPI, GitHub, apt and
others). The design is open, so parts, code, content types and views can all change. The one hard restriction
is the judge, which is built so a change cannot reward-hack its way through.

## Parts

| Part | Project | Does |
| --- | --- | --- |
| Store | Workbench, in `workbench/` (built to leave as its own project) | the store and the model: typed items with claims beside every value (who said it, from which source, quoting it), vocabularies and SSSOM mappings; a desktop-like shell, an API, extractors, live updates, MCP for agents |
| Actor | Claude Code | explores, interviews, builds, maps |
| Judge | [Morphogen](https://github.com/OpenReplicant/Morphogen), cloned to `repos/morphogen` | a change lands only with a verdict the changer cannot reach |

This repository is the glue: scripts that bring the parts up and connect them, a tools container they run in,
and `catalog-info.yaml`, substrate's map of itself.

Production choices substrate stays compatible with but does not run (a model gateway, Prometheus,
OpenTelemetry, Backstage, Nomad, OpenBao, a bus, a console) are options in its own catalog
(`catalog-info.yaml`, system `options`; [`docs/spec.md`](docs/spec.md) section 8). Each says where it fits, the
interface that keeps it possible, when to bring it back, and the commit to restore it from.

**Pluggable by slots, not by trust.** Each part on the map fills a slot named by an interface (the runtime's
verbs, the secrets verbs, Workbench's API, the model endpoint, the graph endpoint), and anything that answers the
interface can take its place once it passes that slot's contract test. Choosing a filler is research
(`docs/choices/`). The judge is the exception: Morphogen is plugged in but not a slot, so the loop can never
choose or tune what judges it ([`docs/spec.md`](docs/spec.md) section 4).

## Where it is going

[`docs/spec.md`](docs/spec.md) is what substrate is meant to become, and [`docs/build.yaml`](docs/build.yaml)
its build plan: cut to the core, one loop on itself, a content system for the model, catalogs to choose from
(done), then substrate observed as it actually runs (machine, containers, settings, APIs, UIs), a graph view
over that (traversal, SPARQL and inference over the same tables), the machine and its agents as a second system,
and slots enforced by contract tests. Left in place, they make Claude Code sessions here build it out a step at a time (the `build-out`
skill). `python3 scripts/spec.py status` shows where it stands; deleting `docs/spec.md` stops it.

## Start

Clone this repository, open Claude Code in it, and ask it to set up (the `setup` skill). By hand:

```sh
git clone https://github.com/OpenReplicant/Substrate substrate && cd substrate
scripts/bootstrap.sh          # host check, Morphogen (and kernel, an option) cloned into repos/, the tools container
scripts/up.sh                 # the stack, Workbench, substrate's plugin and extractors, Claude Code's wiring
scripts/check.sh              # is everything up and wired
```

The host needs git, python3 (the scripts use its standard library), Podman (or Docker) with compose, and
Claude Code. Everything else runs in containers (S-19).

## Layout

```
CLAUDE.md            instructions for the agent working here
DECISIONS.md         every default and why (S-01...), append-only
catalog-info.yaml    the map: what runs (core), what it can choose (options), where to search (sources)
morphogen.yaml       the same map as Morphogen cells
repos.yaml           the upstream projects and the commits last checked
docs/                the spec and its build plan
deploy/              the stack (compose.yaml), the Postgres image, the Caddyfile, the secrets list, the tools image
workbench/           Workbench: the store, its shell, server and MCP (its own README, licence and tests)
plugins/substrate/   substrate's Workbench plugin: content types, extractors, the Map
scripts/             bootstrap, up, down, check, logs, tools, spec, verdicts, map
bin/                 morphogen, gitleaks: each runs inside the tools container
upstream/            fixes prepared for Morphogen (or kernel), not yet opened as PRs
.claude/skills/      setup, build-out, upstream
repos/               Morphogen and kernel clones (gitignored; each its own git repository)
```

## Working upstream

Fixes and improvements to Morphogen (or kernel) go to those repositories by branch and pull request (the
`upstream` skill), never as patches left in a clone.

## Licence

Apache-2.0, as Workbench, kernel and Morphogen.
