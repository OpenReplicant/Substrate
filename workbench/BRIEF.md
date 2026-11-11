# Workbench: brief

*Working name. Status: W1 to W4 done (2026-11-08/09, S-54 to S-57): Substrate's store since S-57. The owner agreed the decisions in section 10.*

A small content system on Postgres with a desktop-like UI, extended by plugins. Content types are real tables;
every value can say where it came from, through a claims table beside them; vocabularies and their mappings are
content too. Extractors mine sources into any of these, not only claims. It is built inside Substrate first and
written so it can leave as its own project: Substrate becomes one plugin among others.

## 0. What it is for

A general-purpose CMS, AI-first (owner, 2026-11-08: "a nice general-use CMS with badass plugin/extensibility...
the CMS world could use a shakeup with an AI-first design"). AI-first means concrete things here: every value
carries its provenance, so an agent's writes are attributed and reviewable exactly as a person's are; agents are
users with roles; extraction and a review lane are core concepts, not add-ons; content types are themselves
content an agent can propose. Substrate is one plugin on it, and nothing in the core knows about Substrate.

The desktop shell is also a launcher: other tools' web UIs open as apps inside it, so a set of disjointed
UIs is used from one place (owner: "tie together a bunch of disjointed UIs with iframes and launch them from a
unified UI").

## 1. Why, and what it replaces

Kernel models everything as claims: one generic entity table of names, every fact a subject-predicate-object
claim, every write a validated change set under a per-module role, with a review lane, belief and clearance on
top. That fits an organisation's knowledge base. It fits typed records (components, skills, packages, people)
badly, which is why "it should be a CMS" kept coming back, and its ceremony arrives before any work does.

What is worth keeping is small, and Workbench keeps it:

- **provenance on every value**: who or what said it, from which source, with the quote;
- **supersede, never overwrite**: conflicting statements sit side by side until one is chosen;
- **vocabularies with mappings** between them (SSSOM);
- **entity resolution and claim deduplication**;
- **a record of each decision**.

None of these needs everything to be a claim. Kernel was parked (S-52), then retired.

## 2. The store

One Postgres, the image Substrate already builds (pgvector, pg_cron, pgmq, pgGraph; kernel D-94). Schema `wb`
for the system's own tables; schema `content` for one table per content type.

| Table | Holds |
| --- | --- |
| `wb.content_type` | each type a plugin registers: id, plugin, label, field schema (JSON Schema), version |
| `content.<type>` | the items of one type, with real columns: `id`, `slug`, `title`, the type's fields, `created_at`, `updated_at` |
| `wb.relation` | typed links between items: (from type, from id, predicate, to type, to id), who stated it (author, run, source); each also a claim in `wb.claim`; the graph pgGraph projects |
| `wb.source` | what was read: URI, sha256, media type, when, where the bytes are kept |
| `wb.run` | one extractor run: extractor, plugin, version, inputs, started and ended, outcome |
| `wb.claim` | the evidence layer: subject (type, id), field or predicate, value or object, source, quote and span, run, observed at, valid from and to, status (`current`, `superseded`, `retracted`, `disputed`), superseded by, confidence |
| `wb.term` | vocabulary terms: IRI, label, kind (class, property, datatype-property, value, prefix), vocabulary, parents, characteristics (transitive, symmetric, ...), inverse, domain, range, the relation predicate a property names, the plugin that loaded it |
| `wb.mapping` | SSSOM mappings between terms: subject, predicate (`skos:exactMatch`, `closeMatch`, ...), object, `mapping_justification`, confidence, author, mapping set |
| `wb.decision` | the review lane: what was decided (a gap, a dispute, a merge, a proposal), the evidence, status, decided by, note |
| `wb.embedding` | vectors for items, claims or sources (pgvector), per model |
| `wb.user` | sign-in: name, password hash (pgcrypto `crypt`, bcrypt), role (`owner`, `editor`, `viewer`, each a Postgres role); `workbench user add|reset` from the command line |

**Items and claims.** An item's columns are its current values; the claims are why. Every write records a
claim, whether an extractor made it or a person typed it, so any field can answer "where did this come from?".
The current value is the newest current claim from the strongest source, unless a person pinned one. A
conflict between sources marks the claims `disputed` and opens a decision. Claims are deduplicated by a hash of
(subject, field, value, source), so re-reading an unchanged source changes nothing.

**Entity resolution.** Two items that may be the same thing become a `wb.mapping` between them with its
justification and confidence; a confirmed one merges them, keeping both ids and every claim. Splink (MIT) is a
candidate resolver plugin.

**Terms.** Workbench's own vocabulary (`workbench/vocabulary.yaml`: wb:Item, wb:Claim, wb:relatedTo, ...) and each
plugin's (`vocabulary:` in plugin.yaml) are loaded into `wb.term`. A content type and each field name their term
with `x-term` (a CURIE or IRI), a field may say which class each of its values names (`x-class-of-value`), and
whatever names none gets a default under `https://workbench.local/`. A plugin's SSSOM mappings (`mappings:` in plugin.yaml, SSSOM TSV with its YAML header) are loaded into
`wb.mapping` with it, CURIEs expanded against the file's `curie_map`, replacing what that plugin's files said before
(migration 014). A relation's term is the property whose
`predicate` names it, else wb:relatedTo.

**A relation is a claim**, like a value: an extractor's run states its relations (`wb.replace_relations`) and
what it stated before and no longer does is retracted. A claim may name its premises (`span.premises`); when a
claim is retracted, everything resting on it is retracted too, and a retracted relation claim takes its row.

**Projections, generated from the terms** (`workbench graph mapping DIR`, `workbench graph project`): pgGraph over
every content type with `wb.relation` between them, so a path follows relations in their direction
(`api.graph_path`); an Ontop mapping and OWL ontology for SPARQL over the live tables; pgvector over
`wb.embedding`; Postgres full-text over titles, fields and quotes. Each is a query or view, rebuildable, never
the truth.

**Rules live in Postgres**, so every client gets them, whether that's the UI, a plugin, an agent or curl.
Triggers record a claim for every insert and update, attributed to the signed-in user from the request's JWT or
to the extractor's run. Row-level security applies each role's rights. Content tables are written only through
the API (PostgREST, section 7); nothing writes around it. Nothing is deleted except by an explicit redaction, which is itself a recorded decision. An item can be retired
(`api.retire`, migration 011): the claims behind it are retracted, the retirement is a claim with its note, and
`api.restore` undoes it; `wb.live` says whether an item stands.
A content type's schema changes additively by default; a destructive change is a migration the owner runs.

## 3. Extractors

An extractor reads a source and emits any mix of **items, relations, claims and sources**, under one run.
Plugins provide them: targeted (a catalog file, Claude Code's skills and hooks, a package manifest, Morphogen's
evidence log) or catch-all (a model reading a document or a transcript, quoting what it took). An interview is
a source, and each answer is a claim attributed to the person. Something acting within a run (a handler the run called, say) writes values as
itself with `ctx.as_author(name)`: its claims are its own, under a run of its own recorded as within the extractor's.

## 4. The UI

One mental model, an IDE's rather than a desktop's, so the concepts do not blur:

| Part | Its one job |
| --- | --- |
| **Sidebar** | where things live, WordPress-style: fixed sections (Workspace, Content, Review, Apps, System); plugins add entries; every content type appears under Content; it collapses to icons |
| **Workspace** | where work happens: views open as tabs (Dockview); split to compare, float or pop out on request; a plain tab group by default; the layout is saved per person; the URL names the active tab |
| **Inspector** | context for the current selection, on the right: first where each value came from (claims, newest first, superseded ones faded), then the item's facts; plugins add sections |
| **Dashboard** | a home tab of widget cards in a responsive grid (sizes s, m, l); plugins add cards; not a free-form canvas |
| **Command palette** | Ctrl/Cmd K: commands, and items by title across every type; the fast path once there are many types |
| **Apps** | other web UIs launched from the sidebar: in a tab (an iframe) when they allow framing from this origin, else in their own window |

The **selection** (type, item, field) is the only shared state: views set it, inspectors follow it.

Extension points are separate, named kinds, each with one small contract: views, widgets, inspector sections,
field editors (chosen by JSON Schema type and format), commands, menu entries, apps (README.md, "Client
plugins"). The core's own screens are a plugin on the same calls.

**How the page is built.** Caddy serves `index.html` as a template (its `templates` handler, 2.11.7: `listFiles`,
`fileExists`, `include`): it finds the installed plugins in `/plugins`, lists each one's `web/index.js` and
includes each one's `web/views.html`, so adding a plugin is adding a folder, with no build step and no registry
call. Data is never rendered on the server: sign-in tokens live in the browser, and one rendering path (Alpine
over the JSON API) is simpler than two. A plugin that wants server-rendered HTML (an HTMX-style flow) will get a
view kind that fetches a fragment with the person's token and starts Alpine in it; Alpine AJAX
(`@imacrayon/alpine-ajax`, MIT) is the candidate, to be checked against the CSP build when a plugin server first
returns HTML (W3).

**Libraries.** Alpine.js's CSP build (`@alpinejs/csp` 3.17.5, MIT): no `eval`, so the page runs under a strict
Content-Security-Policy (`script-src 'self'; style-src 'self'`), which matters when plugins share the page; its
limits (no nested assignments or globals in attributes, no `x-html`) push logic into registered components,
which is the cleaner plugin contract anyway. dockview-core 8.6.2 (MIT, no dependencies): its ES module build,
with the stylesheet its UMD build injects extracted into a file, so nothing is inline. GridStack and Golden Layout
are not used.

**Look.** Calm and dense but readable: system fonts, neutral surfaces, one accent, light and dark themes from
CSS tokens that Dockview's variables are mapped onto, so plugins match by using the same tokens.

## 5. Plugins and integrations

A plugin is a folder with a manifest. The core is itself a set of plugins on the same interfaces.

```yaml
# plugin.yaml
id: substrate                     # unique
version: 0.1.0
licence: Apache-2.0
requires: {workbench: "1"}        # the plugin API version it was written for
content_types: [types/*.json]     # JSON Schema per type: fields, relations, which field is the title
migrations: [sql/*.sql]           # optional, run once each, in order
server: substrate_plugin          # optional Python module with register(wb)
client: web/index.js              # optional ES module: panels, widgets, commands, menu
```

**Database side (SQL).** A plugin's `migrations` add tables, views, functions and triggers. A function in an
exposed schema becomes an endpoint at `/api/rpc/<name>` with no server code. Most plugin logic belongs here.

**Server side (Python), for what SQL cannot do.** `register(wb)` may call `wb.content_type(...)`, `wb.extractor(name, fn)`,
`wb.route(path, handler)` (under `/api/plugins/<id>/`), `wb.on(event, fn)` (item and claim changes,
decisions) and `wb.task(name, fn, schedule)`. An extractor is `fn(source, ctx) -> iterable of records`; `ctx`
records the run and writes through the API.

**Client side (ES module).** The default export lists `panels` (each `{id, title, mount(el, ctx)}` returning an
unmount function), `widgets` (dashboard pieces, same shape), `commands` and `menu` entries. `ctx` gives `api`
(the REST client), `open(panelId, params)`, `events` (subscribe to live changes), `user` and `settings`.

**Integrations.** Everything a panel does goes through PostgREST's JSON API, which publishes its own OpenAPI
description at `/api/`, filtered by the caller's role. So any tool can do what a panel does. An MCP server over the same API lets agents (Claude Code) read and write as a named user. Events
leave through webhooks or pgmq queues when a plugin asks for them.

**Versioning.** The plugin API is `1`. A breaking change raises it, and the core keeps serving the previous one
for a release.

## 6. Built to leave

- Everything lives under `workbench/`, with its own `README.md`, `LICENSE` (Apache-2.0), `pyproject.toml`,
  `Containerfile` and tests. Nothing in it imports from Substrate.
- Substrate's part is a plugin outside it, `plugins/substrate/`: content types (component, skill, hook,
  option, source registry), extractors (the catalog file, Claude Code's project files, Morphogen's evidence
  log), panels (the map, drift between declared and observed, trace).
- The Postgres image stays Substrate's for now; on leaving, Workbench takes a copy of its Containerfile.
- Breaking out means moving `workbench/` to its own repository and cloning it into `repos/`, as Morphogen
  is.

## 7. Services

```
browser ──▶ Caddy (front door) ──┬─ /            the shell: static files (Alpine.js, Dockview, plugin modules)
                                 ├─ /api/*       PostgREST ──▶ Postgres (content.*, wb.*, rpc functions)
                                 └─ /wb/*        workbench server (Python): plugins, extractors, events, MCP ──▶ Postgres
```

- **Postgres** holds the data and the rules: tables, views, triggers that record claims, row-level security per
  role, and SQL functions for sign-in (`login` returns a JWT), recording claims and deciding review items.
- **PostgREST** turns that schema into the API: tables and views as endpoints, functions as `/rpc/<name>`, the
  JWT's `role` claim as the Postgres role for each request, and an OpenAPI description. There is no hand-written
  data API. After a migration, `NOTIFY pgrst, 'reload schema'` refreshes it.
- **Caddy** is the one address: TLS when public, static files, routing. It is the same Caddy the stack
  runs now.
- **The workbench server** (Python) does what SQL cannot do. It loads plugins: it runs their migrations, turns
  their JSON Schema types into tables, and serves their client modules. It also runs extractors (they write
  through PostgREST, with a run of their own), streams events from LISTEN/NOTIFY as Server-Sent Events, and
  offers MCP for agents.

**Recall** is one query over three things, each read as the caller: words (`api.search`, full-text over every
text field and claim quote), meaning (vectors in `wb.embedding`, one per item per model, made outside Postgres
by `workbench embed` through any OpenAI-style embeddings endpoint, `WORKBENCH_EMBED_*`, and made again when the
item's text or the model changes) and the graph (items up to two relations from the ten best matches, scored by
the matches they hang from). `api.recall` fuses the three ranked lists by reciprocal rank and says which found
each item (`via`); without an embedding model it is words and the graph. MCP's `search` tool is recall.

Sign-in follows PostgREST's own pattern (its v16.5 docs, `how-tos/sql-user-management.rst`, read from its
repository): passwords hashed with pgcrypto's `crypt` and `gen_salt('bf')`, and a `login` function that checks
them and signs a JWT with pgjwt's `sign`. pgjwt is one SQL file that needs only pgcrypto, so Workbench vendors
its `pgjwt--0.2.0.sql` with its MIT licence. The JWT secret is a setting in `.env`.

| Part | Licence | Pin (two weeks or older) |
| --- | --- | --- |
| PostgREST | MIT | `docker.io/postgrest/postgrest:v16.5` (2026-10-20) |
| Caddy | Apache-2.0 | 2.11.7 |
| pgjwt | MIT | 0.2.0 (SQL, vendored) |
| Alpine.js | MIT | 3.17.5 (2026-10-20) |
| dockview-core | MIT | 8.6.2 (2026-10-25) |
| Starlette | BSD-3-Clause | 1.10.0 (2026-10-24) |
| Uvicorn | BSD-3-Clause | 0.54.0 (2026-09-25) |
| psycopg | LGPL-3.0 (library) | 3.3.6 (2026-09-18) |
| jsonschema | MIT | 4.26.0 (2026-01-07) |

All of them are permissive, or LGPL as a library.

## 8. Alternatives considered (GitHub, 2026-11-08)

| Project | Licence | Why not as the base |
| --- | --- | --- |
| Payload | MIT | The closest: content types, an admin UI, plugins, auth, Postgres. But it is Next.js and TypeScript end to end, has no claims or provenance layer, and its admin is CRUD screens, not a window manager. Its collection and plugin config are worth borrowing |
| PostgREST | MIT | Adopted as the API layer (section 7), not as the whole project: it does not do claims, extractors or a UI |
| Supabase | Apache-2.0 | A whole platform (auth, storage, functions); far more than one owner's system needs |
| Directus, Strapi | not plainly permissive (GitHub reports NOASSERTION; Directus set aside in S-39) | fails the licence rule |
| Graphiti | Apache-2.0 | Temporal knowledge graphs for agents, claims-shaped, on Neo4j, FalkorDB or Kuzu, not Postgres |
| Cognee | Apache-2.0 | Memory pipelines for agents; Postgres and pgvector for storage, with the graph elsewhere; claims-shaped |

## 9. Build order

| # | Step | Done when |
| --- | --- | --- |
| W1 | Store, API, sign-in | migrations create `wb.*`; a content type registered from a plugin gets its table; PostgREST creates, edits and lists items behind Caddy, a trigger records a claim for every write, and a viewer cannot write; `workbench user add owner` and signing in through `/api/rpc/login` work |
| W2 | Shell and core panels | the sidebar, Dockview workspace, inspector, dashboard, command palette, content list, item editor with claims beside each field, claims, review lane, content types and apps run under a strict CSP; plugins are found by Caddy's template; a layout survives a reload |
| W3 | Server, extractors, live events, Substrate's plugin | the server loads plugins' Python; extractors run from the command line and off a pgmq queue, writing claims with source, quote and span; NOTIFY reaches the browser as Server-Sent Events behind the same JWT; `plugins/substrate` reads `catalog-info.yaml` and `.claude/`, and its drift raises gaps the Map and the review lane show |
| W4 | Kernel leaves the stack | everything Substrate used kernel for runs on Workbench: Morphogen's verdicts as claims (an extractor over its evidence log), recall (full-text, then pgvector), and an MCP server for agents over the same API; kernel stops in `deploy/compose.yaml` and becomes an option |

## 10. For the owner

1. **The name.** Workbench is a placeholder.
2. **Roles.** One owner, plus optional editors and viewers, without per-scope clearance. Kernel's clearance
   could return as a plugin if more than one organisation shares a store.
3. **Kernel.** Retired: it left the stack at W4, and its data with it later.
