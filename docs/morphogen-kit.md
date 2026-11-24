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

## The files

- **The map:** Backstage entity files (Component, API, Resource, System, Group), the format Substrate's
  `catalog/` already uses and Morphogen already reads. Each part's role and the interfaces it provides and
  requires are in its entity; where a claim came from is an annotation or a linked evidence note.
- **A catalog entry:** one file per option for a role: what it is, the interfaces it provides and requires, its
  adjustable parameters (name, type, range, what it does), its licence, and a link to its docs; how it was
  measured against the need when it was tested.
- **The targets:** `morphogen.yaml`, unchanged: cells, what may change, how each is run and judged.

The open question for the PR: whether the map's entity files and `morphogen.yaml` stay two files (the map
describes, the cells say what may change), or the cells are annotations on the map's entities. Recommended: two
files, with the `map` skill writing the first and drafting the second from it, so Morphogen's cell format stays
as it is.

## What moves

1. Substrate's `map`, `catalog` and `research` skills go into `repos/morphogen/skills/`, rewritten to read and
   write files instead of calling `mcp__kernel__*`; Morphogen's `map` skill and Substrate's are merged into one.
2. The catalog entry's format (above) is written down in Morphogen's `schemas/`, beside the cell file's.
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
