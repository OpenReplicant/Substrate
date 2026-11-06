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
| Prometheus | container `prometheus` | the gateway's metrics, read by kernel's observer |

## Getting a machine going

Use the `setup` skill (`.claude/skills/setup/SKILL.md`). It walks the owner through bootstrap, the stack,
the gateway's providers, routing Claude Code through the gateway, and the MCP connections, checking each
step before the next. Run it whenever the owner says "set up", "start the stack", or a check fails.

## Where work goes

- **Glue** (this repository): `scripts/`, `deploy/`, `services/backstage/`, `modules/` (kernel modules that
  connect the parts, briefs first), `catalog-info.yaml` (the map).
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
3. **Both engines.** Every script and compose file works with `CONTAINER_ENGINE=podman` (the owner's
   default) and `docker`. Test a change to `scripts/` or `deploy/` with the engine in `.env`, and say which.
4. **Licences:** permissive or LGPL libraries in the default stack (kernel D-11). Check before adding.
5. **Every change ends with `scripts/check.sh` passing**, or with the failure named and explained.
6. **Do not route your own session through the gateway untested.** `scripts/gateway.py on` changes how
   the next Claude Code session reaches models. First prove the gateway answers (the setup skill's step 5),
   and tell the owner how to undo it (`scripts/gateway.py off`).
7. **The map is the source.** When a part is added, removed or changes how it is filled, update
   `catalog-info.yaml`, then confirm `uv run --project repos/morphogen morphogen structure check morphogen.yaml`
   reports no errors.

## Working with the owner

- Recommend one option and keep moving; ask only for decisions that are theirs (positioning, licences,
  kernel changes, spending money). Say what you recommend when you ask.
- Plain words. Don't write "...and it's worth...".
- Decisions go in `DECISIONS.md` as new rows (append-only; supersede, never edit).

## Commands

```sh
scripts/bootstrap.sh            # once per machine: tools, clones, .venv
scripts/up.sh [PROJECT]         # the stack, then kk up on PROJECT (default: this repository)
scripts/check.sh                # is everything up and wired
scripts/gateway.py on|off|status [--mode subscription|api-key]
scripts/backstage-build.sh      # rebuild the Backstage image after changing services/backstage
scripts/down.sh [--volumes]     # stop (and, asked twice, delete data)
python3 scripts/render_bifrost.py   # after changing provider keys in .env; then restart bifrost
```

Kernel's command is `.venv/bin/kk`; Morphogen's is `uv run --project repos/morphogen morphogen`.
