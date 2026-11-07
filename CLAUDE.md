# Substrate

A business, or any system, that keeps a cited model of itself, notices when practice drifts from intent,
and improves only on evidence it cannot fake. Substrate assembles projects that each do one part and adds
the glue (S-01, S-11). Read `README.md` for the picture and `DECISIONS.md` for every default and why.

| Part | Where | Role |
| --- | --- | --- |
| kernel | `repos/kernel` (its own git repo) | the world model: claims in Postgres, encoders, verifiers, recall, review lane, MAPE-K |
| Morphogen | `repos/morphogen` (its own git repo) | the judge: a change lands only with a verdict the changer cannot reach |
| Claude Code | you | the cycle, the builder, the mapper's hands |
| Bifrost | container `bifrost` | the model gateway: Anthropic, OpenRouter, local models; cost measured outside you |
| Backstage | `services/backstage`, container `backstage` | the map people browse; its MCP endpoint lets you query the catalog |
| Front door | `deploy/caddy/`, container `caddy` | Caddy at 127.0.0.1:8080: kernel's UI and MCP, and `/console/`; plugins in `deploy/caddy/plugins.txt` |
| Console | `services/console/`, container `console` | the owner's live page: review lane, verdicts, spend, stack, bus, the spec's progress; kernel sign-in |
| Bus | database `substrate` in kernel's Postgres | pgmq queues (`deploy/bus/queues.txt`): `triggers`, `owner`, `events`; work and notices, never facts |
| Prometheus | container `prometheus` | the gateway's metrics, read by kernel's observer |
| Tools | `bin/`, container `substrate-tools` | kk, Morphogen, gitleaks, kernel's MCP server and hooks, run in a container as you |
| Runtime | `scripts/runtime/`, `deploy/` | what runs the services: `compose` or `nomad` (`RUNTIME` in `.env`), Podman or Docker (`CONTAINER_ENGINE`) |

## Getting a machine going

Use the `setup` skill (`.claude/skills/setup/SKILL.md`). It walks the owner through bootstrap, the stack,
the gateway's providers, routing Claude Code through the gateway, and the MCP connections, checking each
step before the next. Run it whenever the owner says "set up", "start the stack", or a check fails.

## Becoming the spec

`docs/spec.md` is what substrate is meant to become, and `docs/build.yaml` its build plan. While they are in
place, the SessionStart hook (`.claude/settings.json`, `scripts/spec.py hook`) names the next step, and
sessions work through the plan with the `build-out` skill (`.claude/skills/build-out/SKILL.md`) unless the owner
asks for something else: setup first (step 0), then one step per session, each ending with its check passing.
The owner stops it by deleting `docs/spec.md` or marking steps `dropped`.

## Where work goes

- **Glue** (this repository): `scripts/`, `deploy/`, `services/` (Backstage, the console), `modules/` (kernel
  modules that connect the parts, briefs first), `catalog-info.yaml` (the map), `docs/` (the spec).
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
2. **Secrets stay in `.env`** (gitignored, mode 600). Never print one into a file that is committed, a
   log, a commit message or chat. `.env.example` lists every setting, empty.
3. **Both runtimes, both engines.** Every script works with `RUNTIME=compose` and `RUNTIME=nomad`, and with
   `CONTAINER_ENGINE=podman` (the owner's default) and `docker`. Scripts call only the runtime's four verbs
   (`rt_up`, `rt_down`, `rt_status`, `rt_logs`); a service added to the stack goes into both
   `deploy/compose.yaml` and `deploy/nomad/substrate.nomad.hcl`. Test a change with what `.env` sets, and say
   which. Nomad is Linux only and BUSL-licensed (S-18): nothing outside `scripts/runtime/nomad.sh` and
   `deploy/nomad/` may require it.
4. **Licences:** permissive or LGPL libraries in the default stack (kernel D-11). Check before adding.
5. **Every change ends with `scripts/check.sh` passing**, or with the failure named and explained.
6. **Do not route your own session through the gateway untested.** `scripts/gateway.py on` changes how
   the next Claude Code session reaches models. First prove the gateway answers (the setup skill's step 5),
   and tell the owner how to undo it (`scripts/gateway.py off`).
7. **The map is the source.** When a part is added, removed or changes how it is filled, update
   `catalog-info.yaml`, then confirm `bin/morphogen structure check morphogen.yaml`
   reports no errors.

## Working with the owner

- Recommend one option and keep moving; ask only for decisions that are theirs (positioning, licences,
  kernel changes, spending money). Say what you recommend when you ask.
- Plain words. Don't write "...and it's worth...".
- Decisions go in `DECISIONS.md` as new rows (append-only; supersede, never edit).

## Commands

```sh
scripts/bootstrap.sh            # once per machine: host tools, clones, images, the tools container
scripts/up.sh [PROJECT]         # the stack, then kk up on PROJECT (default: this repository)
scripts/check.sh                # is everything up and wired
scripts/gateway.py on|off|status [--mode subscription|api-key]
scripts/build.sh [kernel|db|caddy|tools|backstage]   # images, built in containers; backstage after changing services/backstage
scripts/bus.sh                  # the bus: database, pgmq, queues (after adding one to deploy/bus/queues.txt)
python3 scripts/spec.py status|next|set ID STATUS   # where the spec's build plan stands
scripts/tools.sh start|stop|status   # the tools container that bin/ runs in
scripts/logs.sh SERVICE         # a service's recent logs, either runtime
scripts/down.sh [--volumes] [--agent]   # stop (delete data after asking; with nomad, stop the agent)
python3 scripts/render_bifrost.py   # after changing provider keys in .env; then restart bifrost
```

Kernel's command is `bin/kk`; Morphogen's is `bin/morphogen`. Both run inside the `substrate-tools` container,
as do `bin/gitleaks` and kernel's MCP server and hooks (S-19). Install nothing on the host for them: a tool the
scripts need goes into `deploy/tools/Containerfile`. Morphogen's judged runs (judge, tune, measure) start
sandboxes of their own and go through its Claude Code plugin, which runs on the host.
