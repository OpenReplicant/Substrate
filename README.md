# Substrate

An agent (Claude Code) in charge of a system of components, with a map of that system it can check and a judge
it cannot fool. Its own system is on the map too, so it can change itself the same way it changes anything else.

## Why it was built

Coding agents are good at making changes and bad at knowing what they are changing. What they know about a
system lives in the chat and is gone next session. "The tests pass" is a check they can edit. And when they
change their own setup (a skill, a hook, a prompt), nothing records what changed or whether it helped.

Substrate gives the agent three things it usually lacks:

- **A model it can check.** Every fact about a system is a claim: who said it, when, and a quote from the file,
  the running container or the interview it came from. Facts that stop being true are retracted, not
  forgotten.
- **Two halves that disagree out loud.** The map says what the system is meant to be. Observers record what
  actually runs. Where the two differ is a gap, and gaps go to a review lane where a person or the judge
  decides which side changes.
- **A judge outside its reach.** A change that claims to improve something lands only with a verdict from
  [Morphogen](https://github.com/OpenReplicant/Morphogen), which tests it on cases the agent has never seen
  and keeps the rules where the agent cannot edit them.

## What it can do for you

On the machine it was built on, it has:

- **Read what actually runs.** It records containers, images, volumes, settings (by name only, never their
  values), HTTP routes, the APIs and UIs served, and Claude Code's skills and hooks. Each fact quotes the
  snapshot it came from. Snapshots are scanned for secrets before anything reads them.
- **Found what nobody had declared.** On its first look at itself it found five volumes still holding data from
  a stack that had been taken down, and an HTTP API that was on no map. The owner decided each one in the
  review lane, and the record shows who decided, when and why.
- **Answered questions about the system.** It can trace a chain such as "route `/api/*` → the container behind
  it → the database volume its data lands on", and answers SPARQL, graph paths and full-text search over
  the same claims. A rule engine adds what follows from the facts, and withdraws a conclusion when a fact it
  rests on goes.
- **Swapped a part on evidence, not trust.** Each slot (the runtime, the secrets store, the store's APIs,
  the judge's interface) has a contract test. A candidate takes the slot only by passing it: OpenBao passed
  the secrets contract 9 of 9 before it was allowed in as an option.
- **Chosen parts from catalogs, not memory.** It picked its SPARQL endpoint by searching registries, testing a
  shortlist and recording why the others lost (`docs/choices/`).

Not done yet, and next:

- **Interviews.** Most of what a system is *for* lives in people's heads. The next step has the agent
  interview the system's owner, with each answer saved as a claim quoting the transcript, and questions
  drawn from the gaps in the map.
- **A judged change.** Morphogen is wired in, but no change here has been judged by it yet. The first will
  be one that closes a gap in a second system.

## Three ways to start

Once it is up, open Claude Code in this folder. It already knows substrate itself: the map, what runs and the
gaps are in Workbench. From there you can point it at a system in three ways, all through the same loop:

| You have | It starts by | The gaps are |
| --- | --- | --- |
| **A system that exists** (a machine, a stack, a repository) | observing it, then interviewing you about what it is for | what runs but nobody declared, and what was meant but does not run |
| **A system you want** | interviewing you, then writing its map before anything exists | every part not running yet: the build list |
| **A change to substrate itself** | editing its own map | the difference between the new map and what runs, closed by builders and judged |

The last two are the same mechanism. A map written before the system exists is all intent and no
observation, so every part on it is a gap until something builds it. Substrate changing itself is that
mechanism applied to its own map. It does not need a copy of itself.

## Ideas to build on

Each of these is small and uses only what is already here:

- **Map something of yours.** Point `observe.yaml` at another stack, run `scripts/observe.sh`, and see what
  it finds that nobody wrote down.
- **Teach the observer a new kind of software.** A probe in `observe.yaml` says how to read one (Caddy's
  admin API is the example). Postgres, nginx, Kubernetes and systemd units are all open.
- **Fill a slot differently.** Write a filler for the runtime (Docker, Nomad, systemd) or for the secrets
  store, and run `scripts/contract.sh` against it. If it passes, it fits.
- **Bring an option back.** Prometheus, OpenTelemetry, a model gateway and Backstage are in the map with
  where they fit and the commit to restore them from. Each would give the observer more to read.
- **Add a domain.** Workbench is a general store. A plugin with its own content types and one extractor
  (`plugins/substrate/` is the example) makes a new kind of thing modellable: a home lab, a research
  library, a game's rules.
- **Add rules.** The vocabulary's axioms (`plugins/substrate/vocabulary.axioms.yaml`) decide what the
  reasoner concludes. A new rule is a small change you can test.
- **Try to cheat the judge.** Morphogen's red team is meant to catch an agent gaming its verdict. A cheat it
  misses is the most useful bug you can report.

## Parts

| Part | Project | Does |
| --- | --- | --- |
| Store | Workbench, in `workbench/` (built to leave as its own project) | typed items with claims beside every value, vocabularies, a desktop-like shell, an API, extractors, live updates, MCP for agents |
| Actor | Claude Code | explores, interviews, builds, maps |
| Judge | [Morphogen](https://github.com/OpenReplicant/Morphogen), cloned to `repos/morphogen` | a change lands only with a verdict the changer cannot reach |

This repository is the glue: scripts that bring the parts up and connect them, a tools container they run in,
and `catalog-info.yaml`, substrate's map of itself. Production choices it stays compatible with but does not
run are options in that map (system `options`; [`docs/spec.md`](docs/spec.md) section 8).

**Pluggable by slots, not by trust.** Each part fills a slot named by an interface, and anything that answers
the interface can take its place once it passes that slot's contract test. The judge is the exception: the
loop can never choose or tune what judges it ([`docs/spec.md`](docs/spec.md) section 4).

## Start

Clone this repository, open Claude Code in it, and ask it to set up (the `setup` skill). By hand:

```sh
git clone https://github.com/OpenReplicant/Substrate substrate && cd substrate
scripts/bootstrap.sh          # host check, Morphogen cloned into repos/, the images, the tools container
scripts/up.sh                 # the stack, Workbench, substrate's plugin, its first look at itself
scripts/check.sh              # is everything up and wired
```

The host needs git, python3 (the scripts use its standard library), Podman (or Docker) with compose, and
Claude Code. Everything else runs in containers. Tested on Linux with rootless Podman 4.9, on one machine.
Workbench's shell is then at http://127.0.0.1:8080/.

## Where it is going

[`docs/spec.md`](docs/spec.md) is what substrate is meant to become, and [`docs/build.yaml`](docs/build.yaml)
its build plan. While they are in place, Claude Code sessions here work through the plan a step at a time (the
`build-out` skill). `python3 scripts/spec.py status` shows where it stands; deleting `docs/spec.md` stops it.
Every default and the reason for it is in [`DECISIONS.md`](DECISIONS.md).

## Layout

```
CLAUDE.md            instructions for the agent working here
DECISIONS.md         every default and why (S-01...), append-only
catalog-info.yaml    the map: what runs (core), what it can choose (options), where to search (sources)
morphogen.yaml       the same map as Morphogen cells
observe.yaml         what the observer reads on this machine, and how to read each kind of software
repos.yaml           the upstream projects and the commits last checked
docs/                the spec, its build plan, recorded choices
deploy/              the stack (compose.yaml), the Postgres image, the Caddyfile, the secrets list, the tools image
workbench/           Workbench: the store, its shell, server and MCP (its own README, licence and tests)
plugins/substrate/   substrate's Workbench plugin: content types, extractors, the observer, the reasoner, the Map
scripts/             bootstrap, up, down, check, observe, map, contract, trace, graph, spec, verdicts
bin/                 morphogen, gitleaks: each runs inside the tools container (in-tools runs anything else there)
.claude/skills/      setup, build-out, research, upstream
repos/               the Morphogen clone, gitignored, its own git repository
```

## Working upstream

Fixes and improvements to Morphogen go to its repository by branch and pull request (the
`upstream` skill), never as patches left in a clone.

## Licence

Apache-2.0, as Workbench and Morphogen.
