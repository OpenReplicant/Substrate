# Substrate

An agent framework: you put an environment on a system you need, run it, and watch and change it. Its shape is
`docs/framework.md`; what is built next is `docs/plan.md`, the one plan; every default and its reason is in
`DECISIONS.md` (append-only). Read the plan first.

This is the **fresh tree** (S-137). v1 is tagged `v1-final` and its plans are in `docs/archive/`: history, not
plans to work from. v1's databases are kept in the same Postgres volume (`workbench`, `gateway`) and dumped in
`.state/backups/`; what people stated there comes back as data imported into the new store.

| Part | Where | Role |
| --- | --- | --- |
| The store | Postgres (`deploy/postgres`: pgvector, pgmq, pg_cron, pgGraph), database `substrate` | Wikibase's data model with OpenWiki's pinned evidence (S-135): entities, statements with ranks, references, spans, revisions, a page per entity. Built in plan step 3b |
| The real-time environment | pgmq in the same Postgres | streams as topics, a queue per actuator, gates, the channel into Claude Code. Step 3c |
| The model gateway | container `gateway` (Bifrost), `scripts/gateway.py` | every model call goes through it with its caller's key and is recorded there, not by the caller (S-77) |
| Local models | container `ollama` | the store's embeddings; local models later |
| Tools | `bin/`, container `substrate-tools` | the scripts' Python and gitleaks, run in a container as you (S-19) |
| The companion | its own container (S-136), plan step 4 | the first environment: Claude Code on Haiku through the gateway |
| Glue | `scripts/`, `deploy/` | brings the parts up and connects them |

The UI (Workbench's successor; its name is the owner's to decide) comes with the store. `deploy/caddy` and
`deploy/ontop` are kept for it and are not started yet.

## Rules

1. **Look it up, then pin it.** Read a tool's current docs before relying on it (versions, flags, config keys);
   pin exact versions; prefer releases at least two weeks old; record what you pinned and where you read it, in
   `DECISIONS.md` when it is a default.
2. **Core first, open always.** Add a part, code or a view when a plan step's check needs it, and say which.
3. **Choose from catalogs, not memory**: the `research` skill, for any component, library, service or model.
4. **Secrets live in `.env`** (gitignored, mode 600), read through `env_value` and the `sec_*` verbs
   (`scripts/lib.sh`). Never print one into a committed file, a log, a commit message or chat. `.env.example`
   lists every setting, empty; `deploy/secrets.txt` says how each secret is made.
5. **One tested path.** Compose with Podman. Scripts call only the runtime's four verbs (`rt_up`, `rt_down`,
   `rt_status`, `rt_logs`) and keep engine-specific code in `scripts/lib.sh`.
6. **Nothing installed on the host** beyond git, python3 (standard library), the engine and its compose, and
   Claude Code. A tool goes into a container (`deploy/tools/Containerfile`, or the companion's).
7. **Licences:** permissive or LGPL in the default stack. Check before adding.
8. **Every change ends with `scripts/check.sh` passing**, and `scripts/test.sh` where tests exist, or with the
   failure named and explained.
9. **Morphogen is out of the build** while the owner refactors it elsewhere: do not touch `repos/morphogen` or
   depend on it. Fixes to an upstream project go by pull request (the `upstream` skill).

## Working with the owner

- Recommend one option and keep moving; ask only for decisions that are theirs (positioning, licences, privacy,
  spending money, what to build next). Say what you recommend when you ask.
- Plain words; describe the loop plainly rather than reaching for broad framings.
- Decisions go in `DECISIONS.md` as new rows (append-only; supersede, never edit a committed row).
- Use the smallest model that can do a subtask (subagents on Haiku unless judgment is needed).

## Commands

```sh
scripts/bootstrap.sh       # once per machine: host tools, images, the tools container
scripts/up.sh              # the stack (db, gateway, ollama), the tools container, the databases; then check.sh
scripts/check.sh           # is everything up and wired
scripts/test.sh [FILE...]  # the test suites, in the tools container
scripts/build.sh [db|tools]
scripts/logs.sh SERVICE    # db, gateway, ollama
scripts/tools.sh start|stop|status
scripts/down.sh [--volumes]   # stop (deleting data asks first)
python3 scripts/gateway.py render|keys   # the gateway's config from .env and its callers
```
