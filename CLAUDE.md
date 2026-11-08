# Substrate

A super-agent that models a system as cited claims, acts on that model, and changes something (including
itself) only on evidence it cannot fake. Modelling itself makes it autopoietic, modelling other systems makes it
an engineer, adapting to model anything makes it a generalist. Read `README.md` for the picture,
`docs/spec.md` for where it is going, and `DECISIONS.md` for every default and why (S-41 sets the current scope).

| Part | Where | Role |
| --- | --- | --- |
| kernel | `repos/kernel` (its own git repo) | the store and the model: a content system on Postgres, claims as the assertion type, ontologies and aliases as content |
| Morphogen | `repos/morphogen` (its own git repo) | the judge: a change lands only with a verdict the changer cannot reach |
| Claude Code | you | the actor: explorer, interviewer, builder, mapper |
| Tools | `bin/`, container `substrate-tools` | kk, Morphogen, gitleaks, kernel's MCP server and hooks, run in a container as you |
| Glue | `scripts/`, `deploy/`, `modules/`, `catalog-info.yaml` | brings the parts up, connects them, and maps substrate itself |

Everything else (a model gateway, Prometheus, OpenTelemetry, Backstage, Nomad, OpenBao, a bus, a console) is an
option in `catalog-info.yaml` (system `options`, spec section 8): don't build it now, don't close the door on it.

The design is open and science-minded (spec section 2). Parts, code, content types and views can all change.
Claims are hypotheses, and a change is an experiment judged on cases you have not seen. The one hard
restriction is Morphogen: never weaken a check to pass it, never read or tune on held-out cases, never edit
the judge's rules from the change being judged. You are expected to be tempted sometimes; the judge is there
for that.

**In transition.** Until build step 1 (cut to the core) lands, `deploy/`, `scripts/` and `services/` still
carry the earlier stack: Bifrost, Prometheus, the OpenTelemetry collector, Backstage, OpenBao, Nomad, the
console, the bus. Don't extend any of them. If this session is routed through the gateway
(`scripts/gateway.py status`), turn it off (`scripts/gateway.py off`) before Bifrost is removed.

## Getting a machine going

Use the `setup` skill (`.claude/skills/setup/SKILL.md`) whenever the owner says "set up" or "start the stack",
or when a check fails.

## Becoming the spec

`docs/spec.md` is what substrate is meant to become, and `docs/build.yaml` its six-step build plan. While they
are in place, the SessionStart hook (`.claude/settings.json`, `scripts/spec.py hook`) names the next step, and
sessions work through the plan with the `build-out` skill (`.claude/skills/build-out/SKILL.md`) unless the owner
asks for something else, one step per session, each ending with its check passing. The owner stops it by
deleting `docs/spec.md` or marking steps `dropped`.

## Where work goes

- **Glue** (this repository): `scripts/`, `deploy/`, `modules/` (kernel modules that connect the parts, briefs
  first), `catalog-info.yaml` (the map), `docs/` (the spec).
- **Fixes and improvements to kernel or Morphogen** go upstream, in their own repositories, by pull request:
  the `upstream` skill (`.claude/skills/upstream/SKILL.md`). Never patch a clone and leave it: a change in
  `repos/` that is not on a branch with a PR is lost work. Each clone has its own `CLAUDE.md`; read it before
  changing that repository, and follow its rules there (kernel's invariants and "kernel changes are
  off-limits without the owner"; Morphogen's red team first and A/A checks).
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
4. **Secrets live in `.env`** (gitignored, mode 600), read through `env_value` in scripts and `settings.py` in
   Python, so another store can sit behind the same calls later. Never print one into a file that is committed,
   a log, a commit message or chat. `.env.example` lists every setting, empty.
5. **One tested path.** Compose with Podman (the owner's default). Scripts call only the runtime's four verbs
   (`rt_up`, `rt_down`, `rt_status`, `rt_logs`) and keep engine-specific code in `scripts/lib.sh`, so Docker
   or another runtime stays possible without being tested.
6. **Licences:** permissive or LGPL libraries in the default stack (kernel D-11). Check before adding.
7. **Every change ends with `scripts/check.sh` passing**, or with the failure named and explained.
8. **The map is the source.** When a part is added, removed or changes how it is filled, update
   `catalog-info.yaml`, then confirm `bin/morphogen structure check morphogen.yaml` reports no errors.

## Working with the owner

- Recommend one option and keep moving; ask only for decisions that are theirs (positioning, licences,
  kernel changes, spending money, which system or domain to model next). Say what you recommend when you ask.
- Plain words. Don't write "...and it's worth...". Don't reach for broad framings (cognitive architectures,
  organisational models) where a plain description of the loop will do.
- Decisions go in `DECISIONS.md` as new rows (append-only; supersede, never edit).

## Commands

```sh
scripts/bootstrap.sh            # once per machine: host tools, clones, images, the tools container
scripts/up.sh [PROJECT]         # the stack, then kk up on PROJECT (default: this repository)
scripts/check.sh                # is everything up and wired
scripts/build.sh [kernel|db|tools]   # images, built in containers
python3 scripts/spec.py status|next|set ID STATUS   # where the spec's build plan stands
scripts/verdicts.sh [PROJECT]   # Morphogen's verdicts into kernel as claims (also run by a hook after judged runs)
scripts/map.sh [PROJECT]        # catalog-info.yaml into kernel (also run by a hook after edits to it)
scripts/tools.sh start|stop|status   # the tools container that bin/ runs in
scripts/logs.sh SERVICE         # a service's recent logs
scripts/down.sh [--volumes]     # stop (delete data after asking)
```

Kernel's command is `bin/kk`; Morphogen's is `bin/morphogen`. Both run inside the `substrate-tools` container,
as do `bin/gitleaks` and kernel's MCP server and hooks (S-19). Install nothing on the host for them: a tool the
scripts need goes into `deploy/tools/Containerfile`. Morphogen's judged runs (judge, tune, measure) start
sandboxes of their own and go through its Claude Code plugin, which runs on the host.
