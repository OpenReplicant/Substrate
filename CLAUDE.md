# Substrate

An agent framework: you put an environment on a system you need, run it, and watch and change it. Its shape is
`docs/framework.md`; what is built next is `docs/plan.md`, the one plan; every default and its reason is in
`DECISIONS.md` (append-only). Read the plan first.

This is the **fresh tree** (S-137). v1 is tagged `v1-final` and its plans are in `docs/archive/`: history, not
plans to work from. v1's databases are kept in the same Postgres volume (`workbench`, `gateway`) and dumped in
`.state/backups/`; what people stated there comes back as data imported into the new store.

See `docs/repos.md` for what each repository (Kernel, Substrate, MetaSoar, Morphogen) owns.

| Part | Where | Role |
| --- | --- | --- |
| The store | moving to the Knowledge Kernel (S-153, S-154: the UI, skills and tests read it from the kernel's database `kernel`, the agent's tools are the kernel's MCP `substrate` profile; `scripts/kernel.sh`); until the last item of plan step 3d, `store/` (schema in `store/sql/`, agent tools in `store/mcp.py`) on Postgres (`deploy/postgres`: pgvector, pgmq, pg_cron, pgGraph), database `substrate` | Wikibase's data model with OpenWiki's pinned evidence (S-135, S-138): entities, statements with ranks, references, spans, revisions, a page per entity; the agent's tools over MCP, and maps, roles, interfaces and catalogs (S-139; the `map` and `catalog` skills) |
| envkit | `envkit/` (declarations in `envkit/declarations/`; tests: `python3 -m pytest envkit`) | The fast in-process scheduler (lockstep or realtime) for live play, one module contract with `environment/` (S-161); moved from MetaSoar |
| The real-time environment | `environment/` (schema `env` in `store/sql/005_environment.sql`, the channel in `environment/channel.py`) on pgmq in the same Postgres | signals logged whole and fanned out as topics, a queue per actuator behind its gate (`free`, `propose`, `deny`), the channel into Claude Code, archived only on `ack` (S-143) |
| The model gateway | container `gateway` (Bifrost), `scripts/gateway.py` | every model call goes through it with its caller's key and is recorded there, not by the caller (S-77) |
| Local models | container `ollama`; container `llm` (llama.cpp, profile `llm`) | Ollama for the store's embeddings; the local chat model (Gemma 4 26B-A4B from `LLM_MODELS_DIR`) on llama.cpp, at the gateway as `local/gemma` (S-149) |
| Tools | `bin/`, container `substrate-tools` | the scripts' Python and gitleaks, run in a container as you (S-19) |
| The companion | `deploy/companion` (compose service `companion`), `environment/companion.py` (service `environment`), the UI's `#/companion` | the first environment: Claude Code on Haiku through the gateway's pass-through route on the owner's login, fed by the channel; it replies, starts background tasks and proposes budget and model changes (S-136, S-144) |
| The voice head | `voice/` (compose service `voice`, profile `voice`) on 127.0.0.1:8110 | the companion's voice and face: microphone in over a WebSocket, Silero and Parakeet to text, the local model to answer, Kokoro to speak, a face that moves with it; hands real work to the companion (S-147, S-149) |
| Components and the judge | `env.component` and `env.verdict` (`store/sql/007_components.sql`), `environment/author.py`, `environment/judge.py` (compose service `judge`), `judge/cases` (the judge's only) | every version of a component with its card; an author proposes from the record, the judge tests it against the active one on cases the author cannot read, the owner activates (S-151) |
| The UI | `ui/` (`ui/server.py`, `ui/static`), compose service `ui` on 127.0.0.1:8100 | the store's pages and maps as diagrams (S-140), read-only; v1's Workbench rebuilt, with no name of its own (S-141) |
| Glue | `scripts/`, `deploy/` | brings the parts up and connects them |

`deploy/caddy` (in front of the UI) and `deploy/ontop` (SPARQL) are kept and not started yet.

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
7. **Licences:** permissive or LGPL for what the repository contains or links into Substrate's code. A GPL part may
   be a default when it is fetched at setup (never in the repository), runs unmodified in its own container and is
   reached over a process boundary (S-146). Check before adding.
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
scripts/up.sh              # the stack (db, gateway, ollama, ui), the tools container, the databases; then check.sh
scripts/check.sh           # is everything up and wired
scripts/test.sh [FILE...]  # the test suites, in the tools container
scripts/build.sh [db|tools|companion|voice|kernel]
scripts/logs.sh SERVICE    # db, gateway, ollama, ui, environment, companion, llm, voice
scripts/tools.sh start|stop|status
scripts/kernel.sh init|export|login NAME|mcp NAME   # the Knowledge Kernel: schema, one-off export of `store`, an agent's login and its MCP server
scripts/down.sh [--volumes]   # stop (deleting data asks first)
python3 scripts/gateway.py render|keys   # the gateway's config from .env and its callers
bin/in-tools python3 scripts/db.py init|import-v1   # the store's schema; v1's people's statements and decisions
bin/in-tools python3 scripts/env.py waiting|decide|publish|actuators|gate|queues   # the environment, as a person
scripts/companion.sh login|attach|restart|status   # the companion's session (log in once)
```
