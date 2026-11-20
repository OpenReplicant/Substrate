# Substrate store vs Knowledge Kernel: what folding would take

Read-only comparison, 2026-11-20. Neither repository was changed. Paths: **S** = this repository,
**K** = the Knowledge Kernel's repository (main at efbdec2). `K:001` = K/kernel/schema/001_kernel.sql, `S:001` = S/store/sql/001_store.sql.
"Module" means the kernel rule (K/CLAUDE.md "Rules": modules read `api` views, write only by `submit_change_set`,
may keep derived tables in their own schema; `kernel/schema/` is frozen v0, K/docs/spec.md:64-68, K/CLAUDE.md:15).
Where I could not tell, I say "unclear".

## 1. What each store is

**Store A: Substrate's store** (schema `store`, S/store/sql/001-004; DECISIONS.md:145 S-135, :148 S-138)
- Data model: Wikibase in Postgres. `entity` (Q items, P properties with datatype, key, label, aliases, prose; S:001:30-41),
  `statement` (typed value, rank; S:001:140-151), `qualifier` (155-165), shared `reference` + `cites` + `premise` (289-316),
  `source`/`span` with sha256 (66-82), `revision` snapshots (565-574). Derived views: `usable` (364), `flag` (371), `violation` (395), `page` (541).
- Writes: plain SQL by whoever holds a connection. Rules are triggers: value must fit datatype (S:001:168-260), a statement
  needs a reference at commit (352-360), values are fixed, nothing is deleted (242-285), `store.actor` must be set (592-604).
  Agents write through `store.mcp` (`create_item`, `say`, `deprecate`; S/store/mcp.py:54-65), synchronous, one transaction.
- Permissions: none inside the store. MCP connects as `postgres` (DECISIONS.md:148 "connects as `postgres` for now"); the UI uses a
  read-only session (:150). Only the `env` schema has roles (`env_agent`, `env_judge`; S/store/sql/006_logins.sql:110-123, 007:137-142).
  Rule in code, not DB: a client deprecates only its own statements, a person reviews the rest (S/store/mcp.py:143-150).
- Provenance: reference = who (parser run, interpreter + version, person, rule + premise statements) + pinned span (S:001:289-349).
  A claim is "a statement whose reference is an interpreter" (docs/framework.md:42-45). The MCP client's name/version from `initialize` becomes the interpreter (mcp.py:91-93).
- MCP tools (10): search, read, expand, locate, path, alternatives, violations, create_item, say, deprecate (S/store/mcp.py:36-65).

**Store B: the Knowledge Kernel** (schema `kernel` + `api`, K:001; K/docs/spec.md:64-186)
- Data model: five primitives (K:001:85-225): `entity` (an IRI only; meaning comes from claims), `claim` (subject, predicate, object entity or JSON-LD value,
  qualifiers jsonb, valid_from/to, scope, evidence_type, attribution, run, change set, statement_key), `artifact` (sha256, immutable), `run`, `change_set`;
  side tables `claim_reference`, `claim_derivation`, `claim_status`, `belief`, `verification`, `redaction`.
- Writes: only by change set (`api.submit_change_set`, K:001:848). States submitted, valid, awaiting_review, approved, applied (K:001:391-441). A validator
  module role validates, a reviewer approves the review lane, `kernel.apply_change_set` (448-630) applies all ops or none. Asynchronous (spec.md:119-135).
- Permissions: every agent is a Postgres role mapped to an agent IRI (K:001:61, 306-333); scopes and `scope_grant` (69-82); RLS on every claim table (745-785);
  validator != submitter, reviewer != submitter, verifier != producer (K:001:407-430, apply 593-605); only stewards redact (706-718).
- Provenance: every claim has agent + run + change set; needs a reference or `derived_from` (apply KK032); extracted claims need a quote (KK033); references are
  Web-Annotation quote/prefix/suffix/span (K:001:165-175); scope may not be wider than inputs (KK035/KK037). Bi-temporal: valid_from/to vs recorded_at (spec.md:84-85).
- MCP tools: operator profile has 16 (query_claims, get_entity, search, explain, list_slots, list_modules, start_run, submit_change_set, get_change_set,
  list_runs, finish_run, whoami, list_change_sets, review_queue, review, graph; K/modules/kernel-mcp/kernel_mcp/server.py:170-324) plus the memory profile
  remember, recall, changes_since (memory.py:120, 191, 229); a profile is chosen per login (server.py:45-48, `PROFILES`).

## 2. Capability table

| capability | Substrate store | kernel | gap (what the kernel would need) |
|---|---|---|---|
| entity / statement model | `entity` with Q/P ids, key, label, aliases, prose (S:001:30); `statement` rows | `entity` = IRI only (K:001:85); `claim` (K:001:139) | Label, aliases, description, prose are claims (`rdfs:label`, `skos:altLabel`, `skos:definition` are approved in K/kernel/schema/002_bootstrap.sql:62, 73-74). Map key to an IRI, keep the Q/P number as a claim. Statement uuids are not preserved: `add_claim` has no id field (K:001:486-520). |
| ranks / status | `rank` preferred/normal/deprecated, the only column of a statement that may change (S:001:147, 251-253); `usable` view (364) | `claim_status` append-only history, same three values (K:001:184); no usable view | Port `usable` as an `api` view over `api.claims.status`. `claim_status.reason` is a closed list (superseded, refuted, retracted, review, belief); Substrate's free-text "reason for deprecated rank" (S:001:643) has no home. |
| revisions / history | one `revision` per entity per transaction, full snapshot, who + summary (S:001:565-604) | History is the claims plus `claim_status` plus `recorded_at`; no per-entity snapshot; change set has no summary field | A read view "entity as of time T" and "revisions of entity". Summary: use `run.info` (K:001:101). |
| references, quotes, spans | shared `reference` row; span = source + locator + text + hash (S:001:73-82, 289-301) | `claim_reference`: artifact or source_uri, quote, prefix, suffix, span selector (K:001:165) | Map 1:1 for quotes. Locator and span hash go in `claim_reference.span` jsonb (free form). Not shared across claims (one row per claim). |
| span hashing; flag what cites a changed source | pinned spans; `read_source` supersedes changed spans (S:001:108-136); `flag` view is recursive over premises (371-384); `stale_file_spans` (S/store/__init__.py:292) | Artifacts are sha256 and immutable (K:001:125). Truth-maintenance flags claims derived from a withdrawn claim (K/docs/decisions.md:98, D-90b). Nothing watches a source changing. | A processor module: new artifact for the same `source_uri` or a span hash mismatch -> verification `inconclusive` on citing claims; truth-maintenance already carries it down `derived_from`. Needs an artifact read view (none in `api`). |
| typed values | `check_value`: item, property, string, quantity (amount, unit, bounds), time (Wikidata form + precision), coordinate, url, external-id; write fails otherwise (S:001:168-240) | `object_value` is a JSON-LD value object `{@value,@type}` (K:001:144); the kernel checks no datatype; SHACL validator blocks the change set (K/modules/validator-shacl/validator/core.py:134-157) | Encode quantity, time precision, coordinate as JSON-LD plus qualifiers; write SHACL shapes in a pack. No write-time guarantee inside the kernel (validator must run). Round trip with Wikidata form is lossy unless the pack defines it. |
| qualifiers | `qualifier` rows, ordered, typed (S:001:155) | `claim.qualifiers` jsonb keyed by property IRI (K:001:145) | Keyed object: no order, and a repeated qualifier property per statement cannot be expressed (S allows several rows with the same property). Unclear how often Substrate uses repeats; check data. |
| constraints: reported, not blocking | `violation` view, four kinds, never blocks (S:001:395-426) | SHACL in the validator; a violation makes the change set invalid, i.e. blocking (core.py:145 `allow_warnings=False`) | A processor module that reports (annotation claims or an `api` view) and a shapes pack. The kernel's own validator is the wrong place. |
| pages per entity (Markdown) | `store.render` and cached `store.page` with tsvector (S:001:490-548) | none. D-101 / K/docs/content.md:58-76 propose item views and `put_revision`, "proposed", only `memory-extractor/eval/run.py` mentions it | Module: a page renderer into its own schema, with RLS by scope. Markdown prose could be an artifact (content.md:35) but its predicate is an open question (content.md:115-117). |
| bi-temporal times | none on statements; `created_at` only. Times are values (point in time, S/store/sql/003_components.sql:9, 37). framework.md:35-44 says Graphiti-style four times, but the store does not have them | `valid_from/to` and `recorded_at` (K:001:146-155); `claim_status` history | Kernel is ahead. Nothing needed; the import sets recorded_at = now unless a column is carried. |
| confidence / belief | none in the store (grep: no confidence column) | `belief` table, model per run, `api.claims.belief` (K:001:195, 803-812); belief-corroboration module | Kernel is ahead. Substrate claims would just start with no belief. |
| review lane | "a person prefers or deprecates" (docs/framework.md:44-45); MCP tool refuses to deprecate others' statements (mcp.py:143-150) | change-set lane `review` forced by `needs_review` for vocabulary claims (K:001:339-351), reviewer role approves (K:001:419-431) | Lane forcing only looks at `add_claim` (K:001:342-343). To force review on `set_status` to `preferred` needs a validator rule (module) or a schema change. `set_status` checks only scope, not who made the claim (K:001:561-579). |
| retraction / redaction | no redaction. Deprecate with a reason; nothing deleted (S:001:242-285) | status reason `retracted`; `redaction` blanks values, keeps lineage (K:001:706-743) | Kernel is ahead. Substrate's "locate" must tolerate blanked rows. |
| row-level security | none (S:001 has no policy); MCP as `postgres` | RLS on all claim tables by scope (K:001:745-785) | Kernel is ahead. Cost: every Substrate login/agent needs a role, agent row and scope grant (`kk agent add`, K/kk/cli.py:315-323). Substrate's MCP names clients by `initialize` info (mcp.py:158-160); kernel has no such dynamic agent. |
| graph (pgGraph) | pgGraph straight over `store.entity` and `store.statement`; `store.graph_path` (S/store/sql/002_graph.sql:13-23) | pgGraph is in the image (D-94, K/docs/decisions.md:102). `current_edge` proposed (D-86 :94, M6-T0 milestone-6.md:45); not in schema (grep of K/kernel/schema finds none) | Needs `kernel.current_edge`, which is a kernel change the owner pre-approved only in D-87 (:95) and is not built. Without it: pgGraph over a module-owned edge table fed from `api.claims`. |
| vectors (pgvector) | `span.embedding`, `page.embedding` columns, unused; model parked (S:001:81, 546; DECISIONS.md:152 S-142) | `recall_dense` schema, 384-dim, hybrid with BM25 (K/modules/recall-dense/migration.sql:39, 62) | Exists as a module; one fixed model per index. Nothing to build until S-142 is reopened. |
| full text | `store.page.tsv` (simple) and trigram on label (S:001:42, 544-561) | `recall.doc` tsvector + BM25 per scope (K/modules/recall-index/migration.sql:12-40); `search` tool (server.py:196) | Search is over claims, not pages. Entity-label fuzzy search (pg_trgm) and page text search come with the page module. |
| SPARQL / Ontop | planned, not built: "Ontop's RDF ... not yet" (DECISIONS.md:148); `deploy/ontop/Containerfile` only | none. `kk export` writes N-Quads (K/kk/cli.py:333). No Ontop anywhere in K (grep) | Neither store has it. Kernel's N-Quads export is the nearest; Ontop mapping would be a new module. Unclear whether the owner still wants Ontop (S-137 dropped the old mapping, DECISIONS.md:147). |
| maps / roles / interfaces / catalogs | vocabulary of properties and classes (has-part, requires-interface, provides-interface, ...; S/store/sql/003:18-48), `store.alternatives` (003:87), `store.map`, `store.map_nodes` (004:17, 46) | no equivalent. K has `kkt:` TOSCA terms (hasRequirement, hasCapability, dependsOn, memberOf) and Backstage pack (D-100, :108) and `graph` tool | Vocabulary pack (properties must be typed via review lane, K:001:636) plus mappings (SKOS) to kkt:/backstage terms; `alternatives` and `map` re-written as `api` views/functions in a module. Open question: reuse `kkt:hasRequirement/hasCapability` or keep Substrate's terms. |
| MCP tools | see section 1 (10 tools, synchronous writes) | 16 operator tools + 3 memory tools, writes via `submit_change_set` | New `substrate` profile in kernel-mcp: same tool names, bodies over `api` views and change sets. The write path is asynchronous: a validator must run or `say` returns "submitted", not an id. |
| imports from v1 | `store/import_v1.py` (v1 claims by people and Claude Code -> statements; 45 decisions) | `kk import` reads kernel N-Quads only (K/kk/cli.py:334) | One-off: already imported into the store, so the job is store -> kernel, not v1 -> kernel. Retire `import_v1.py` after the move. |
| tests | `scripts/tests/test_store.py` (72 checks per DECISIONS.md:150), `test_ui.py` (26) | 30 schema checks (K/docs/spec.md:66, K/kernel/schema/tests/run.sh); module tests under K/modules/*/tests | Port the 72 store checks to run against the kernel through the new profile. |

Not in the table but real: Substrate's `env` schema (pgmq queues, actuators, components, verdicts; S/store/sql/005-007) lives in the same
database and migration folder. It is not knowledge-store content and the kernel has no equivalent (see section 4).

## 3. Module or kernel schema change, gap by gap

Kernel rule: `kernel/schema/` is frozen; a change needs the owner (K/CLAUDE.md:15, 36-38). Everything below is a module unless marked **SCHEMA**.

| gap | verdict | specifics |
|---|---|---|
| Entity labels, aliases, prose, Q/P ids | module (pack + importer) | Claims with `rdfs:label`, `skos:altLabel`, `skos:definition`; the Q/P number as `skos:notation` (new term, review lane); prose as artifact or claim, predicate open (content.md:115). |
| Properties and datatypes as governed vocabulary | module | `rdf:type rdf:Property` claims go to review (K:001:636-646, setting `review_types` 002_bootstrap.sql:34-37); datatype as `rdfs:range`. Same discipline as Substrate's "properties are governed" (mcp.py:7-8). |
| usable value, entity-as-of, revisions | module | `api` views from a module migration (spec.md:152, precedent K/modules/verifier-quotes/migration.sql:19-22). |
| Pages, page search, trigram label search | module | Derived tables in the module's own schema with RLS by scope, like `recall` (recall-index/migration.sql:1-8). |
| Typed values | module for shapes; **limit** | Pack with SHACL shapes. Kernel cannot refuse a malformed value itself: the validator module can. A write-time guarantee in the kernel would be **SCHEMA**; recommend not asking. |
| Qualifier repeats and order | **SCHEMA** only if Substrate needs it | `qualifiers` is a keyed object (K:001:145). Work-around: a list value under one key. Check the data first. |
| Free-text deprecation reason | module work-around, else **SCHEMA** | `claim_status.reason` is a closed enum (K:001:188); store the text as a claim about the claim (IRI of the claim) or in `run.info`. A `note` column on `claim_status` would be a schema change. |
| "Only a person prefers; a client deprecates only its own" | module (validator rule) | `set_status` checks scope only (K:001:561-579). A validator module can mark such change sets invalid; forcing the review lane by setting is **SCHEMA** because `needs_review` reads `add_claim` only (K:001:339-351). |
| Span pinning and "what cites a changed source" | module | Processor reading artifacts and `claim_references`, writing `inconclusive` verifications; truth-maintenance already propagates (D-90b). Needs an `api` view on `kernel.artifact` (agents have select on the table, K:001:787-791, but modules should read `api`). Verification rule KK050 ("no method verifies its own output") must allow the watcher: it is a different module from the claim's producer, so fine. |
| Constraints reported, not blocking | module | Processor/view reading shapes + `api.claims`; validator stays blocking. |
| Maps, `alternatives`, `map_nodes` | module | Views/functions over `api.claims`; terms from a pack. |
| Synchronous writes | module (`kk serve` validator) or accept async | Auto lane still needs a validator to move `submitted` to `valid` (K:001:410-420). Run the validator as part of `kk serve`; a tool can poll `get_change_set`. |
| Graph | **SCHEMA** (D-86 `current_edge`, owner-pre-approved but unbuilt) or module edge table | Module edge table fed from `api.claims` works now but must handle supersede and redaction itself. |
| Revisions with summary | module | `run.info`. |
| Per-client agent identity from MCP `initialize` | module/ops | Not possible in the kernel (one role per agent); mint one login per client (`kk agent add`). |
| Ontop / SPARQL | new module, unclear need | Not built on either side. |
| Redaction, belief, bi-temporal, RLS | nothing | Kernel already has them. |

Net: no mandatory schema change was found. Three optional asks for the owner: `current_edge` (D-86), a `reason`/note on `claim_status`, `set_status` in `needs_review`.

## 4. What in Substrate calls its store today (what must be repointed)

Searched S excluding `store/`, DECISIONS.md, docs/archive, .state.

Knowledge-store tables and functions (must move to kernel views):
- `S/ui/server.py`: `store.search` (:84), `store.usable` + `store.entity` + `store.key('has-part')` (:88-89, :98), `store.entity` (:93), `store.render` (:97), `store.map_nodes` (:101), `store.map` (:102). Also the module docstring :11-13, and `from store.mcp import database_url` (:54).
- `S/scripts/check.sh:32-40`: counts `store.entity`, `store.statement`, `store.flag`; calls `store.stale_file_spans`; reads `public.store_migration` (:34) and `store.SQL` (:35).
- `S/scripts/db.py:51-54, :92-93`: `store.migrate`, `store.project` (pgGraph build), `import_v1`.
- `S/scripts/tests/test_store.py` (store API throughout, e.g. :31-32, :69, :109-117, :233-234, :277-320, :324-345) and `S/scripts/tests/test_ui.py:26-27, :126`.
- `S/scripts/trials/embedding-model/trial.py:4, 62, 80` (`store.page`) and `S/scripts/trials/map-diagram/cases.py:2, 20-21` (`store.map_nodes`, `store.map`): one-off trials, can be left.
- `S/.claude/skills/map/SKILL.md:8` and `S/.claude/skills/catalog/SKILL.md:8, 28` use the MCP tools as `mcp__store__*` and name `create_item`, `say`, `search`. `S/.claude/skills/research/SKILL.md:13` reads Substrate's map through `search`/`read`.
- `.mcp.json` registers the server (DECISIONS.md:148) but is gitignored (S/.gitignore:11) and absent here; its exact content is unknown.
- Docs naming the store: S/CLAUDE.md:13, docs/plan.md:31, docs/framework.md:18-55, 162-172.

Not store tables, but coupled to the `store/` package (retiring `store/` breaks them unless moved):
- `S/environment/channel.py:27` imports `VERSIONS, database_url, obj` from `store.mcp`; `environment/author.py:21`, `companion.py:39`, `judge.py:33` import `database_url`. They use only `env.*` functions (`env.active_component`, `env.submit_component`, `env.record_verdict`, `env.claim_component`, ...).
- `S/voice/server.py:123-159`: connects with `STORE_URL`, uses `env.publish`, `env.action`, `env.active_component` only.
- `S/ui/server.py:136-144` (conversation, `env.action`, `env.signal`, `env.actuator`, `env.current`, components) is `env`, not store.
- `S/deploy/compose.yaml:132, 159, 183, 269` and `S/deploy/companion/start.sh:15-20` pass `STORE_URL` (database `substrate`). The companion's MCP is `substrate` (channel.py), not the store tools.
- `S/store/sql/005-007_*.sql` are the `env` schema and share `store.migrate` (S/store/__init__.py:28-40). They have to keep a home and a migrator.
- Unclear: whether the kernel will live in the same database `substrate` or in its own (K compose uses database `kk`, D-94 `cron.database_name=kk`). That decides whether `STORE_URL` splits in two. Both images carry pgvector, pgmq, pg_cron, pgGraph (S/DECISIONS.md:147, K/docs/decisions.md:102).
- `S/.claude/skills/setup/SKILL.md:13` only says the store arrives in plan step 3b (a stale line to edit); `upstream` has no store references.

## 5. Recommended order (shortest path first)

0. **Ask the owner three things** (about 15 minutes): (a) one database or two; (b) do we ask for `current_edge`, a status note, and `set_status` review forcing (or live with validator rules); (c) Ontop and vectors stay parked. Nothing else blocks.
1. **Vocabulary pack `substrate`** (module): Wikibase-style terms plus has-part, role, interface, catalog, goal, verdict from S/store/sql/003:18-48, with SKOS mappings to `kkt:` and the backstage pack. Goes through the review lane.
2. **One-off exporter store -> kernel** (script, not a module): reads `store.*`, writes change sets: entities, statements as claims, ranks as `set_status`, references as `claim_reference`, rule premises as `claim_derivation`, spans as artifacts. Mapping: parser -> `deterministic`, interpreter -> `extracted`/`inferred`, person -> `testimony`, rule -> `inferred`. Record a Q/P to IRI table so docs and skills still resolve. Dry-run into a scratch kernel first.
3. **Read-model module `substrate-views`**: `usable`, entity pages with search, `map`, `map_nodes`, `alternatives`, entity-as-of. Smallest set to run the UI unchanged: `search`, `render`, `map`, `map_nodes`, `usable`.
4. **`substrate` profile in kernel-mcp** with the same ten tool names; writes through `submit_change_set`; validator in `kk serve`. Mint kernel logins for Claude Code and the companion.
5. **Repoint** S/ui/server.py (:84-102), S/scripts/check.sh, the `map`/`catalog`/`research` skills, tests (port the 72 checks), `.mcp.json`. Keep `env` working: move S/store/sql/005-007 and `store.migrate` to `environment/` (`env` schema) and re-export `database_url`, `VERSIONS`, `obj` (channel.py:27 and three more).
6. **Span-change watcher** (module) and the reported-constraints processor. These are the two behaviours Substrate has that the kernel lacks entirely.
7. **Graph**: wait for `current_edge`, else a module edge table. Port `store.graph_path` and `path` tool.
8. **Retire `store/`**: delete `store/sql/001-004`, `import_v1.py`, `mcp.py` after the tests pass on the kernel; keep a backup dump of schema `store` (S-137 did the same for v1, DECISIONS.md:147).

Biggest risks: (1) asynchronous writes change how `say` feels to agents; (2) RLS means every writer needs a role and scope; (3) typed values are only as strict as the SHACL pack; (4) the `env` schema is tangled with `store/`; (5) statement uuids change, so any cited uuid in docs or skills breaks.
