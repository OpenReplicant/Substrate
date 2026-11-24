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

## The files: two

- **The map and its option catalogs:** Backstage entity files (Component, API, Resource, System, Group), the
  format Substrate's `catalog/` already uses and Morphogen already reads (`backstage:` in `morphogen.yaml`). Each
  part's role and the interfaces it provides and requires are in its entity; where a claim came from is an
  annotation or a linked evidence note. Annotations move from `substrate.dev/*` to a neutral prefix.
- **An option for a role is an ordinary Component**, not a new kind, so stock Backstage and the kernel's
  `encoder-backstage` read it unchanged: `spec.lifecycle: candidate`, the interfaces it provides and requires in
  the usual fields (so the fit check works), and our own fields under one namespaced key in `spec` (`spec.morphogen`:
  the part it could fill, its adjustable parameters as JSON Schema, its licence, its docs link, how it was
  evaluated). Checked 2026-11-24 in Backstage's Component schema (no `additionalProperties` on `spec`) and its
  "extending the model" page: the catalog "will happily store whatever is in it" in a spec; annotation values
  must be strings; a new kind or `apiVersion` needs a catalog processor, which this avoids. One key keeps us clear
  of fields Backstage may add later, the risk that page names.
- **The cells:** `morphogen.yaml`, the optimisation envelope, unchanged: cells, what may change, how each is run,
  measured and scored, and which tests must keep passing. It already goes beyond any one optimiser: the selector
  chooses scope, optimiser and measure, and adapters hand a cell to GEPA, Optuna, OpenEvolve, AFlow or a Claude Code
  worker. A cell's settings bounds can be checked against the option's parameter schema: the catalog says what can
  be tuned, the cell what this run may tune.

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
2. The option's fields (`spec.morphogen`, above) are written down as a schema in Morphogen's `schemas/`, beside the cell file's.
3. Morphogen's README and BRIEF say what it is now: the kit, with the judge at its core.
4. In Substrate afterwards: the three skills are removed from `.claude/skills/` (Substrate uses the plugin like
   any user); `setup` and `upstream` stay, since they are about this repository.

## What does not change

- The judge, its independence, the cell contract, the evidence log.
- The kernel: when a user wants indexing, search or graph traversal, its `encoder-backstage` ingests the same
  files. The kit never requires it.
- Substrate's running parts (the environment, the router, the channel, the desktop, the assistant): they are
  built on the kernel and the kit (S-209 d).

## What it is for (S-210)

Mapping an SMB's organisation and systems, finding where to optimise, and writing each opportunity up as an
implementation project: in an engagement with the client's material and access, or as prospecting on public
sources before a first call. The kit is the product; the business itself is worked in its own session.
