# Substrate: the seed

The spec for what Substrate is from here (S-155, 2026-11-18). It replaces the framework in
`docs/framework.md` as the description of this repository; that page stays as the record of how we got here,
and its environment, components and pass-through now belong to the targets Substrate builds, not to Substrate.

## What it is

**The primitives for emergence, scoped as a coding and devops tool.** Substrate maps a system, builds toward
what the map says it should be, reconciles what is left, and hands every change to a gate. Point it at a
repository and it works on it the way an active developer would. Point it at itself and it is
self-modifying; that is a choice of target, not a different design.

Owner, 2026-11-18: "the seed doesn't need all the tooling, just the primitives for emergence. Substrate can
expand in its base project repo to cover all the usecases of interest with skills, tools, recommended stack,
etc... but we keep it scoped, and use it to build out other repos (which will carry artifacts any substrate
instance can work with)". Generalising beyond software is a later plan it can write from its own matured
design.

It is not a harness (Claude Code, or any harness, runs it), not a cognitive architecture (it can build one:
Soar is its first target, `docs/soar.md`), and not a judge (Morphogen is, from its own repository).

## Three roles inside, one outside

| Role | Does | Form |
| --- | --- | --- |
| **Mapper** | turns sources into maps with evidence: decomposition into parts, the role each plays, the interfaces that make parts interchangeable, goals with metrics; and catalogs of alternatives for each role | the `map`, `catalog` and `research` skills, carried over and trimmed |
| **Builder** | closes the gap from the blueprint to what is observed | ordinary coding-agent work, with whatever tooling helps |
| **Reconciler** | reads the gaps that remain: errors, shortcomings, edge cases, optimisations; turns them into changes to the blueprint or work for the builder | a skill, new |
| **Judge** (outside) | decides whether a change is really better, on cases the builder cannot reach | **Morphogen**, `OpenReplicant/Morphogen`: its own repository, container and CI runner, a GitHub App whose check branch protection requires |

The judge is never inside the bundle: anything Substrate ships, the builder can reach.

## Three kinds of map, and the gaps between them

| Kind | From | Example |
| --- | --- | --- |
| **Blueprint** (designed) | specs, designs, decisions | `docs/soar.md` |
| **Described** (hypothesised) | interviews, docs, what people say | "orders go to finance, then shipping" |
| **Observed** (measured) | code, logs, traces, trials | what the code does; how long a step takes |

Blueprint against observed is what is left to build or what is broken; described against observed is where
people's picture is wrong; blueprint against described is where the design misses what people need. The loop:
map, build, observe, reconcile, judge, and map again.

## Files, not a database

Every harness works on a filesystem; Morphogen reads files from the base commit; git is the record and the gate.
So the seed keeps everything in files:

| Need | Form |
| --- | --- |
| The map | Backstage descriptor files (`catalog-info.yaml`): `Component`, `System`, `Domain`, `API`, `Resource` with `dependsOn`, `providesApis`, `consumesApis`; what Backstage lacks (roles, interfaces other than APIs, goals) as custom kinds under `openreplicant.com/v1alpha1` *(to confirm against Backstage's descriptor spec before writing the first file)* |
| Evidence | on each claim: source, locator, the quoted text and its hash, as annotations; a check script rehashes them and lists what has gone stale |
| Catalogs | candidates as entities in the same files; their measurements as trial output files and Morphogen's verdicts |
| Working memory | plain files: notes, the plan, the reconciler's open gaps |
| Long-term memory | git history and Morphogen's evidence log |

An index (SQLite, say) is added only when a measurement says searching the files is too slow, and is a cache
rebuilt from them, never the truth. Postgres belongs to targets that need it (Soar's working memory first).

**Ontologies** are adopted only where a tool or a person on the other side speaks one: ArchiMate, BPMN or OCEL,
OpenTelemetry, SOSA/SSN, PROV, an API's own spec. Choosing the vocabulary for a new domain is a step of the
mapper, made from candidates like any other choice. There is no upper ontology.

## Two ways in

1. **The plugin**, for a person working in Claude Code: the skills and agents above, installed from GitHub.
2. **An MCP server**, for any agent that wants to change itself or something it runs: it speaks intent and KPIs
   to Substrate as a person would.

| Tool | The agent gives | It gets |
| --- | --- | --- |
| `improve` | intent, KPIs, the target (a repository, path or config), constraints | a ticket, at once |
| `status` | a ticket | where it stands: mapped, proposals built, judged, waiting at the gate, merged or refused |
| `explain` | a change | what changed, why, the measurements and the verdict |
| `revert` | a change | the previous version, through the same gate |

Results also arrive as pushed events, as the channel does today. A Soar agent at an impasse no rule and no LLM
substate resolves can call `improve` on its own architecture; nothing in the seed treats that case specially.

## The gate

Set per target, in the owner's policy committed on the target's base branch:

1. Morphogen and a person: a verdict, then a person merges.
2. Morphogen and auto-merge: a pass merges (Morphogen's `autonomy` by lifecycle).
3. A person only: a pull request, no judge.
4. Full auto: no judge, no person; allowed, labelled Goodhart-exposed in every record it leaves.

**The rule:** whoever asks for a change (a person, an agent through `improve`, Substrate itself) may state intent
and KPIs, never how they are measured or which gate applies. Both come from the target's base, as Morphogen's
rules do; a change to either is a change like any other, gated by the policy already in force.

## Targets carry their own artifacts

A repository Substrate builds keeps, in itself: its specs (blueprints), its `catalog-info.yaml` (its map), its
`morphogen.yaml` (cells, what may change, how better is measured), its gate policy. Any Substrate instance can
pick it up from those alone. The first is the Soar repository (`docs/soar.md`).

## What this tree keeps, and where the rest goes

| Kept here | Moves to the Soar repository as parts it may reuse | Retired |
| --- | --- | --- |
| the skills (`map`, `catalog`, `research`, `upstream`, `setup` trimmed); the trials and their results; `DECISIONS.md`; the gateway's config (`scripts/gateway.py`); `docs/privacy.md` | the store (`store/`, its schema, `store/mcp.py`), the environment (`environment/`, schema `env`, the channel), the companion, the voice head, the local model's service, the UI | `environment/judge.py` and `environment/author.py` (Morphogen judges; authors are whatever proposes); `env.component` and `env.verdict` |

Moved, not deleted: the move happens when the Soar repository exists to receive them, in one commit each side.

## Open

- The custom kinds' exact shape, once Backstage's descriptor spec is read.
- The reconciler's first version: what it reads and what it writes.
- The MCP server's transport and auth when the asking agent is not on this machine.
- How Morphogen's own `map` skill (drafting cells) and Substrate's mapper meet: Substrate writes the catalog,
  Morphogen reads it (its Backstage loader), and Morphogen's skill becomes a view of that.
