# The map

A system's map says what it is meant to be: its parts, what each is for, what it provides and needs, and how it
is recognised running. It is written in Backstage's catalog entity model (kinds Domain, System, Component,
Resource, AiResource, API, Group), because those kinds and a free `type` on each cover anything that can be
changed: a service, a library, a skill, a hook, a parameter, a prompt.

## Where it lives

**Workbench holds the map.** Each entity is a `component` item, each field a column, every value a claim saying
who wrote it, when and from what. Edit it there:

- in Workbench's shell (the item's page), or
- over MCP: `save_item` (type `component`, the slug, the fields), `retire_item` to take an entry off the map
  (nothing is deleted: its claims are retracted, with your note), `restore_item` to undo that.

A hook (`.claude/settings.json`, `scripts/map.sh --hook`) runs after each of those MCP writes on a component and
derives what follows: the map's relations (`substrate:map`), drift against what runs (`substrate:drift`), and
inferences (`substrate:reasoner`). `scripts/map.sh` does the same by hand.

**The file is an export.** `scripts/map.sh export` writes a domain's entities to a catalog file
(`catalog-info.yaml` for the domain `substrate`), in a fixed order, so exporting an unchanged map gives the same
bytes. It is committed for three reasons:

1. **The judge reads it.** Morphogen takes its rules from the base commit, `morphogen.yaml` names this file, and a
   candidate that edits it is refused. The map in Workbench can be written by the agent, so the judge never reads
   it there. A map change reaches the judge only when its export is committed, and map changes are the owner's
   decision (spec section 7).
2. **A new machine starts from it.** The first `scripts/up.sh` on an empty Workbench imports it
   (`scripts/map.sh import`), so a clone starts knowing itself.
3. **Its history is git's.** A diff of the export is a readable record of how the map changed, beside the claims.

`scripts/check.sh` says when the map in Workbench and the committed file differ. Importing a file over a map that
was edited in Workbench is refused unless forced (`scripts/map.sh import --force`), so a stale file cannot
quietly undo edits.

**Other systems' maps stay in Workbench.** A map of the owner's machine, or of a system someone is planning, is
theirs: export it only where they say (`scripts/map.sh export DOMAIN FILE`), never into this public repository.

## How the fields map

| Workbench field | Backstage | Becomes the relation |
| --- | --- | --- |
| `kind`, `description`, `annotations`, title | `kind`, `metadata.description`, `metadata.annotations`, `metadata.title` | |
| `type`, `lifecycle`, `definition`, `children` | `spec.type`, `spec.lifecycle`, `spec.definition` (an API's), `spec.children` (a Group's) | |
| `owner` | `spec.owner` | ownedBy |
| `system`, `domain`, `subcomponent_of` | `spec.system`, `spec.domain`, `spec.subcomponentOf` | partOf |
| `depends_on` | `spec.dependsOn` | dependsOn |
| `provides_apis`, `consumes_apis` | `spec.providesApis`, `spec.consumesApis` | providesApi, consumesApi |

The slug is the entity's name for components, resources and AI resources (so a skill's entry and the skill meet),
and `<kind>-<name>` for the other kinds (`system-core`, `api-runtime-api`), since a system and a component may share
a name.

## Substrate's own map

Three systems in the domain `substrate` (S-47):

- `core`: what runs (Workbench, Morphogen, Claude Code, and the glue)
- `options`: components substrate can choose when a step needs one (lifecycle `option`); none of them runs now
- `sources`: catalogs of catalogs, registries to search when no known component fits (lifecycle `listed`)

## Annotations

| Annotation | On | Says |
| --- | --- | --- |
| `substrate.dev/intent` | any part | what the part is for |
| `substrate.dev/fill` | any part | `existing` (built, in Workbench, Morphogen or Claude Code), `adopt` (open source as is), `build` (to write) |
| `substrate.dev/basis` | any part | where an existing part lives |
| `substrate.dev/step` | any part | the build step (`docs/build.yaml`) it belongs to |
| `substrate.dev/filler` | a part filling a slot | which filler it is, as `scripts/contract.sh` names it (`compose`, `env`, `openbao`, ...) |
| `substrate.dev/observed-as` | any part | how it is recognised running: `<type>:<slug>` items `substrate:observed` reads, comma-separated, a slug may be a glob; drift raises what no part accounts for (`OBSERVE.md`) |
| `morphogen.dev/tests` | an API | the slot's contract test, which any filler must pass; Morphogen runs it |
| `substrate.dev/fits`, `interface`, `when`, `restore`, `evidence`, `candidates` | an option | where it would sit, what keeps it possible now, what would bring it back, the commit and paths to restore it from, what was learned running it, the candidates |
| `substrate.dev/search`, `gives`, `limits`, `checked` | a source | how to search it, what metadata it returns, what to know first, when the endpoint last answered |
