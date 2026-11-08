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
| Kernel | [kernel](https://github.com/OpenReplicant/kernel), cloned to `repos/kernel` | the store and the model: a content system on Postgres, with claims as the assertion type and ontologies and aliases as content and taxonomy |
| Actor | Claude Code | explores, interviews, builds, maps |
| Judge | [Morphogen](https://github.com/OpenReplicant/Morphogen), cloned to `repos/morphogen` | a change lands only with a verdict the changer cannot reach |

This repository is the glue: scripts that bring the parts up and connect them, a tools container they run in,
and `catalog-info.yaml`, substrate's map of itself.

Production choices substrate stays compatible with but does not run (a model gateway, Prometheus,
OpenTelemetry, Backstage, Nomad, OpenBao, a bus, a console) are options in its own catalog
(`catalog-info.yaml`, system `options`; [`docs/spec.md`](docs/spec.md) section 8). Each says where it fits, the
interface that keeps it possible, when to bring it back, and the commit to restore it from.

## Where it is going

[`docs/spec.md`](docs/spec.md) is what substrate is meant to become, and [`docs/build.yaml`](docs/build.yaml)
its build plan: cut to the core, one loop on itself, kernel as a content system, catalogs to choose from,
another system beside itself. Left in place, they make Claude Code sessions here build it out a step at a time (the `build-out`
skill). `python3 scripts/spec.py status` shows where it stands; deleting `docs/spec.md` stops it.

## Start

Clone this repository, open Claude Code in it, and ask it to set up (the `setup` skill). By hand:

```sh
git clone https://github.com/OpenReplicant/Substrate substrate && cd substrate
scripts/bootstrap.sh          # host check, kernel and Morphogen cloned into repos/, the tools container
scripts/up.sh                 # the stack, then kernel connected to this repository
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
deploy/              the compose overlay on kernel's stack; the secrets list; the tools image
modules/             briefs for kernel modules that connect the parts
scripts/             bootstrap, up, down, check, logs, tools, spec, verdicts, map
bin/                 kk, morphogen, gitleaks, kernel-mcp: each runs inside the tools container
upstream/            fixes prepared for kernel or Morphogen, not yet opened as PRs
.claude/skills/      setup, build-out, upstream
repos/               kernel and Morphogen clones (gitignored; each its own git repository)
```

## Working upstream

Fixes and improvements to kernel or Morphogen go to those repositories by branch and pull request (the
`upstream` skill), never as patches left in a clone.

## Licence

Apache-2.0, as kernel and Morphogen.
