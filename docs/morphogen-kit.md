# Morphogen as the kit: map, research, catalog, optimise (S-209)

A proposal for a pull request to Morphogen (rule 9, the `upstream` skill). Nothing moves until the owner has
reviewed it. The decision is S-209; the business reason is S-210.

## What changes, in one paragraph

Morphogen today is "a judge for self-improving systems", and its README says tools that describe a system sit
above it. The kit puts the describing in the same plugin: Morphogen maps a system, researches and catalogues the
options for each part, and optimises behind its judge. The judge stays the core and stays independent, because
what an optimiser may edit is still only what a cell's `change` names; the mapping and cataloguing skills write
the map and the catalog, which the judge already reads from the base commit and which no candidate may touch.
Everything is files on the harness the user chooses. No database, no kernel.

## The four jobs

| Job | What it does | Where it is today | In the kit |
| --- | --- | --- | --- |
| Map | interview a person, do hypothetical design work, find facts through whatever the harness can reach; build the map out and detail substructures iteratively | Morphogen's `map` skill (cells, interfaces, intent as tests); Substrate's `map` skill (parts, roles, interfaces, evidence, written to the kernel) | one `map` skill, writing Backstage entity files with evidence, and the cells drawn from them |
| Research and catalog | search openly for options for each role; document each with its interfaces and adjustable parameters, or a link to its docs once chosen | Substrate's `catalog` and `research` skills, writing to the kernel | `catalog` and `research` skills, writing catalog entries as files |
| Optimise | change a cell, judge it | Morphogen's `morphogen` skill, MCP server and judge | unchanged |
| Orchestrate | delegate and build | the harness itself | nothing to build: the harness, given MCP servers for access |

## The files: one format, and the operator's private file

Everything Morphogen works with that is committed is a **Backstage catalog**, in as many entity files as the project
likes, so it loads into a Backstage web UI when someone wants one and needs no Backstage server otherwise
(Morphogen already reads these files itself). `morphogen.yaml` goes; the projects that use it are our own and are
moved by hand (the owner, 2026-11-24: "I want morphogen to be a clean sensible product").

- **The map:** Components, APIs, Resources, Systems and Groups, with their roles, the interfaces each provides
  and requires, and evidence as annotations or linked notes. Our own fields live under one key, `spec.morphogen`,
  so they never clash with fields Backstage adds later.
- **An option for a role:** an ordinary Component with `spec.lifecycle: candidate`; under `spec.morphogen` the part
  it could fill, its adjustable parameters as JSON Schema, its licence, its docs link and how it was evaluated.
- **A cell:** the entity it judges, with the cell's rules under `spec.morphogen` (`change`, `keep`, `run`, `score`,
  `better`, `tests`, `rounds`, `timeout`, `observe`, `same_output`). A cell below Backstage's grain (a file inside
  a component) is a small Component of its own, nested with Backstage's `subcomponentOf`. The envelope goes beyond
  any one optimiser, as it does now: the selector chooses scope, optimiser and measure; adapters hand a cell to
  GEPA, Optuna, OpenEvolve, AFlow or a Claude Code worker. A cell's settings bounds are checked against the
  parameter schema of the option it uses.
- **An interface's tests:** on its API entity, `spec.morphogen.tests`.
- **The project's settings and shared defaults** (sandbox, image, the judging defaults cells inherit, replacing
  YAML anchors, which do not cross files): on the System entity.
- **The operator's private file**, `morphogen.local.yaml`, stays as it is and outside the catalog: held-out
  answers, private inputs, sandbox, budget. It is never loaded into a UI.

Checked 2026-11-24: Backstage's Component schema leaves `spec` open (no `additionalProperties`) and its "extending
the model" page says the catalog "will happily store whatever is in it"; annotation values must be strings; a new
kind needs a catalog processor, which this avoids. To check before building: that API and System leave `spec`
open the same way. **The judge's protection** must cover every catalog file it reads, not one project file: the
default deny already refuses a change to the map; the PR proves it across files.

## Documentation, as files

Research needs an option's docs, not only a link. A documentation MCP server that turns web documentation into
markdown for agents is recommended (or bundled, if its licence allows), picked with the `research` skill; a local
one first, since a hosted one sends what is looked up off the machine (`docs/privacy.md`). Its output is a folder of
markdown files beside the catalog: Morphogen works with them wherever it is deployed, and the kernel ingests them
deterministically when it is there. Candidates to check, not chosen: arabold's docs-mcp-server, Context7, Firecrawl's
MCP server, the reference `fetch` server, Crawl4AI.

## How it ships

Morphogen is already built in layers, and the kit keeps them:

1. **The core:** the Python package (`morphogen`): the file formats' schemas, the judge, the optimiser adapters (as
   extras: `optuna`, `gepa`), the CLI (`morphogen`) and the MCP server (`morphogen-mcp`). Anyone can integrate it
   by hand or write a package for any harness against it.
2. **The skills:** Agent Skills folders (`map`, `catalog`, `research`, `morphogen`), which any harness that reads
   SKILL.md can load; their scripts and references go in the folders, as the spec allows. They name the MCP
   tools by their server's own names, not one harness's prefix.
3. **Packages per harness:** the Claude Code plugin first (`.claude-plugin/`, which exists), each other harness a
   thin manifest over the same core and skills, written when a user needs it.

## What moves

1. Substrate's `map`, `catalog` and `research` skills go into `repos/morphogen/skills/`, rewritten to read and
   write files instead of calling `mcp__kernel__*`; Morphogen's `map` skill and Substrate's are merged into one.
2. The `spec.morphogen` fields (options, cells, interfaces, the System's settings) are written down as a schema in
   Morphogen's `schemas/`; `morphogen.yaml` is removed, and our projects that use it (Substrate, the demos) are moved
   to the catalog by hand.
3. Morphogen's README and BRIEF say what it is now: the kit, with the judge at its core.
4. In Substrate afterwards: the three skills are removed from `.claude/skills/` (Substrate uses the plugin like
   any user); `setup` and `upstream` stay, since they are about this repository.

## What does not change

- The judge, its independence, what a cell says (only where it is written), the evidence log.
- The kernel: when a user wants indexing, search or graph traversal, its `encoder-backstage` ingests the same
  files. The kit never requires it.
- Substrate's running parts (the environment, the router, the channel, the desktop, the assistant): they are
  built on the kernel and the kit (S-209 d).

## What it is for (S-210)

Mapping an SMB's organisation and systems, finding where to optimise, and writing each opportunity up as an
implementation project: in an engagement with the client's material and access, or as prospecting on public
sources before a first call. The kit is the product; the business itself is worked in its own session.
