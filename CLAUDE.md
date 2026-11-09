# Substrate

A self-modifying agent platform: an agent in charge of a system of components, its own system included. A
component is anything that can be modified (a service, a skill, a hook, a parameter, a prompt), named in the
catalog's entity model. It models each system as cited claims, acts on that model, and changes something only on
evidence it cannot fake. Self is not a special case: substrate is modelled in Workbench like any other system,
so nothing you build here may work only on itself. Read `README.md` for the picture,
`docs/spec.md` for where it is going, and `DECISIONS.md` for every default and why (S-41 sets the current scope).

| Part | Where | Role |
| --- | --- | --- |
| Morphogen | `repos/morphogen` (its own git repo) | the judge: a change lands only with a verdict the changer cannot reach |
| Claude Code | you | the actor: explorer, interviewer, builder, mapper |
| Workbench | `workbench/` (built to leave), containers `db`, `postgrest`, `workbench`, `caddy` | the store and the model: typed tables, claims beside every value, vocabularies and SSSOM mappings; its shell at `/`, PostgREST at `/api`, its server at `/wb/api` (extractors, live events, MCP for you); `workbench/BRIEF.md` |
| Substrate's plugin | `plugins/substrate/` | the content types (component, skill, hook, verdict, what is observed running), extractors (map, claude-code, observed, drift, reasoner, contracts, morphogen) and the Map view; `MAP.md` says how the map is held |
| Tools | `bin/`, container `substrate-tools` | Workbench's command, Morphogen, gitleaks, run in a container as you |
| Glue | `scripts/`, `deploy/`, `catalog-info.yaml` (the map's export) | brings the parts up and connects them; the map itself (what runs, what could, where to search) lives in Workbench |

Everything else (a model gateway, Prometheus, OpenTelemetry, Backstage, Nomad, OpenBao, a console) is an
option on the map (system `options`, spec section 8): don't build it now, don't close the door on it.

The design is open and science-minded (spec section 2). Parts, code, content types and views can all change.
Claims are hypotheses, and a change is an experiment judged on cases you have not seen. The one hard
restriction is Morphogen: never weaken a check to pass it, never read or tune on held-out cases, never edit
the judge's rules from the change being judged. You are expected to be tempted sometimes; the judge is there
for that.

**Workbench is your memory and your map.** Its MCP server (`workbench` in `.mcp.json`) lets you search, read an
item with the claims behind each value, save items (your writes are claims attributed to `claude-code`), and see
and decide the review lane. Changes you make to the repository reach it through the extractors, which the hooks
and `scripts/up.sh` run.

## Getting a machine going

Use the `setup` skill (`.claude/skills/setup/SKILL.md`) whenever the owner says "set up" or "start the stack",
or when a check fails.

## A system of the owner's

Substrate can take on another system beside itself: one that exists (a machine, a stack, a repository), one the
owner wants built, or a change to substrate itself. Use the `interview` skill (`.claude/skills/interview/SKILL.md`)
for any of them; on a first session the SessionStart hook says to offer the three. A system's map is a domain of
its own in Workbench, and stays there: never export another system's map into this repository.

## Becoming the spec

`docs/spec.md` is what substrate is meant to become, and `docs/build.yaml` its build plan. While they
are in place, the SessionStart hook (`.claude/settings.json`, `scripts/spec.py hook`) names the next step, and
sessions work through the plan with the `build-out` skill (`.claude/skills/build-out/SKILL.md`) unless the owner
asks for something else, one step per session, each ending with its check passing. The owner stops it by
deleting `docs/spec.md` or marking steps `dropped`.

## Where work goes

- **Glue** (this repository): `scripts/`, `deploy/`, `plugins/substrate/` (substrate's Workbench plugin),
  `catalog-info.yaml` (the map's committed export), `docs/` (the spec).
- **Workbench** (`workbench/`): a general-purpose CMS that substrate is one plugin on. Nothing in it may know about
  substrate; it is built to leave as its own project.
- **Fixes and improvements to Morphogen** go upstream, in their own repositories, by pull request:
  the `upstream` skill (`.claude/skills/upstream/SKILL.md`). Never patch a clone and leave it: a change in
  `repos/` that is not on a branch with a PR is lost work. Each clone has its own `CLAUDE.md`; read it before
  changing that repository, and follow its rules there (Morphogen's red team first and A/A checks).
- `upstream/<repo>/*.patch` holds changes prepared elsewhere and not yet opened as PRs. Apply one with the
  `upstream` skill, then delete the patch file once its PR is open.

## Rules

1. **Look it up, then pin it.** Read a tool's current docs before relying on it (versions, flags, config
   keys); pin exact versions; prefer releases at least two weeks old; record what you pinned and where you
   read it, in `DECISIONS.md` when it is a default.
2. **Core first, open always.** Add a part, code or a view when a build step's check needs it, and say which.
   A production-grade choice that is not needed yet becomes an option in the map, not code.
3. **Choose from catalogs, not memory.** When picking a component, search the source catalogs
   (`catalog-info.yaml`, system `sources`) and the options, record the candidates with cited claims, test the
   shortlist, and record the pick and the rejections (spec section 5).
4. **Secrets live in `.env`** (gitignored, mode 600), read through `env_value` and the `sec_*` verbs
   (`scripts/lib.sh`), so another store can sit behind the same calls later. Never print one into a file that is committed,
   a log, a commit message or chat. `.env.example` lists every setting, empty.
5. **One tested path.** Compose with Podman (the owner's default). Scripts call only the runtime's four verbs
   (`rt_up`, `rt_down`, `rt_status`, `rt_logs`) and keep engine-specific code in `scripts/lib.sh`, so Docker
   or another runtime stays possible without being tested.
6. **Licences:** permissive or LGPL libraries in the default stack. Check before adding.
7. **Every change ends with `scripts/check.sh` passing**, or with the failure named and explained.
8. **The map is the source, and it lives in Workbench** (`plugins/substrate/MAP.md`). When a part is added,
   removed or changes how it is filled, change its `component` item (MCP `save_item`, `retire_item` to take one
   off), then `scripts/map.sh export` and confirm `bin/morphogen structure check morphogen.yaml` reports no errors.
   Commit the export with the change: Morphogen reads the map from that file at the base commit, never from
   Workbench. Never hand-edit `catalog-info.yaml`; the next export overwrites it.

## Working with the owner

- Recommend one option and keep moving; ask only for decisions that are theirs (positioning, licences,
  changes to the judge, spending money, which system or domain to model next). Say what you recommend when you ask.
- Plain words. Don't write "...and it's worth...". Don't reach for broad framings (cognitive architectures,
  organisational models) where a plain description of the loop will do.
- Decisions go in `DECISIONS.md` as new rows (append-only; supersede, never edit).

## Commands

```sh
scripts/bootstrap.sh            # once per machine: host tools, clones, images, the tools container
scripts/up.sh                   # the stack, Workbench's schema, substrate's plugin and extractors, Claude Code's wiring
scripts/check.sh                # is everything up and wired
scripts/test.sh [FILE...]       # every test suite, each in a throwaway database
scripts/build.sh [db|workbench|tools]   # images, built in containers
python3 scripts/spec.py status|next|set ID STATUS   # where the spec's build plan stands
scripts/verdicts.sh             # Morphogen's verdicts into Workbench (also run by a hook after judged runs)
scripts/map.sh [export|check|import]   # the map's relations, drift, inferences; or the map to and from catalog-info.yaml (MAP.md)
scripts/observe.sh              # what runs on this machine (observe.yaml, and observe.local.yaml: what its owner allows) into Workbench, gitleaks first, then drift
scripts/interview.sh            # interview transcripts (.state/interviews) into the person's own claims, gitleaks first (the interview skill)
scripts/contract.sh INTERFACE [FILLER]|all   # a slot's contract test against a filler (e.g. secrets-api openbao); results into Workbench
scripts/graph.sh                # the graph views (Ontop mapping, pgGraph projection) regenerated from Workbench's terms
scripts/trace.sh NAME [DEPTH]   # an item's chain in Workbench: claims, relations followed out, the part that runs as it, each gap and its decision
scripts/workbench.sh migrate|plugin load DIR|extract PLUGIN:NAME|user add NAME|user reset NAME|user list|token NAME   # Workbench (prints passwords once: the owner runs user add)
python3 scripts/harness.py status|apply   # this project's Claude Code wiring: Workbench's MCP server in .mcp.json
scripts/tools.sh start|stop|status   # the tools container that bin/ runs in
scripts/logs.sh SERVICE         # a service's recent logs
scripts/down.sh [--volumes]     # stop (delete data after asking)
```

Morphogen's command is `bin/morphogen`; it runs inside the `substrate-tools` container, as do `bin/gitleaks` and
Workbench's command (`scripts/workbench.sh`) (S-19). Install nothing on the host for them: a tool the
scripts need goes into `deploy/tools/Containerfile`. Morphogen's judged runs (judge, tune, measure) start
sandboxes of their own and go through its Claude Code plugin, which runs on the host.
