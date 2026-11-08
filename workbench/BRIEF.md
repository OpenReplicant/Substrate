# Workbench: brief

*Working name; the name is the owner's to choose. Status: proposed (2026-11-08), not built.*

A small content system on Postgres with a desktop-like UI, extended by plugins. Content types are real tables;
every value can say where it came from, through a claims table beside them; vocabularies and their mappings are
content too. Extractors mine sources into any of these, not only claims. It is built inside Substrate first and
written so it can leave as its own project: Substrate becomes one plugin among others.

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

None of these needs everything to be a claim. Kernel is parked, not deleted (S-52).

## 2. The store

One Postgres, the image Substrate already builds (pgvector, pg_cron, pgmq, pgGraph; kernel D-94). Schema `wb`
for the system's own tables; schema `content` for one table per content type.

| Table | Holds |
| --- | --- |
| `wb.content_type` | each type a plugin registers: id, plugin, label, field schema (JSON Schema), version |
| `content.<type>` | the items of one type, with real columns: `id`, `slug`, `title`, the type's fields, `created_at`, `updated_at` |
| `wb.relation` | typed links between items: (from type, from id, predicate, to type, to id); the graph pgGraph projects |
| `wb.source` | what was read: URI, sha256, media type, when, where the bytes are kept |
| `wb.run` | one extractor run: extractor, plugin, version, inputs, started and ended, outcome |
| `wb.claim` | the evidence layer: subject (type, id), field or predicate, value or object, source, quote and span, run, observed at, valid from and to, status (`current`, `superseded`, `retracted`, `disputed`), superseded by, confidence |
| `wb.term` | vocabulary terms: IRI, label, kind (class, property, value), vocabulary |
| `wb.mapping` | SSSOM mappings between terms: subject, predicate (`skos:exactMatch`, `closeMatch`, ...), object, `mapping_justification`, confidence, author, mapping set |
| `wb.decision` | the review lane: what was decided (a gap, a dispute, a merge, a proposal), the evidence, status, decided by, note |
| `wb.embedding` | vectors for items, claims or sources (pgvector), per model |
| `wb.user`, `wb.session` | sign-in: name, password hash (scrypt), role (`owner`, `editor`, `viewer`); `workbench user add|reset` from the command line |

**Items and claims.** An item's columns are its current values; the claims are why. Every write records a
claim, whether an extractor made it or a person typed it, so any field can answer "where did this come from?".
The current value is the newest current claim from the strongest source, unless a person pinned one. A
conflict between sources marks the claims `disputed` and opens a decision. Claims are deduplicated by a hash of
(subject, field, value, source), so re-reading an unchanged source changes nothing.

**Entity resolution.** Two items that may be the same thing become a `wb.mapping` between them with its
justification and confidence; a confirmed one merges them, keeping both ids and every claim. Splink (MIT) is a
candidate resolver plugin.

**Projections.** pgGraph over `wb.relation` for neighbourhoods and paths; pgvector over `wb.embedding`;
Postgres full-text over titles, fields and quotes. Each is a query or view, rebuildable, never the truth.

**Rules.** Plugins write through the API, which records the claim and the run; nothing writes the content
tables around it. Nothing is deleted except by an explicit redaction, which is itself a recorded decision.
A content type's schema changes additively by default; a destructive change is a migration the owner runs.

## 3. Extractors

An extractor reads a source and emits any mix of **items, relations, claims and sources**, under one run.
Plugins provide them: targeted (a catalog file, Claude Code's skills and hooks, a package manifest, Morphogen's
evidence log) or catch-all (a model reading a document or a transcript, quoting what it took). An interview is
a source, and each answer is a claim attributed to the person.

## 4. The UI

A desktop in the browser, with WordPress's admin as its starting shape:

- **sidebar menu** built from what plugins register (content types, tools, settings);
- **a window manager** for the work area: panels open as tabs, split, dock, float or pop out into their own
  window, and the arrangement is saved per person (Dockview, below);
- **the dashboard** is a layout of widgets that plugins provide (recent changes, open decisions, gaps,
  extractor runs);
- **core panels**: a content list per type (filter, sort, search), an item editor (a form from the type's
  schema, with each field's claims and sources beside it), the claims explorer, the review lane, a graph view,
  a trace view (a part's chain: observed, declared, gaps, decisions);
- live updates over Server-Sent Events from Postgres's LISTEN/NOTIFY.

**Layout library: Dockview** (`dockview-core`, MIT, no dependencies, vanilla TypeScript API). It handles
docking, tabs, splits, floating groups, pop-out windows and serialisable layouts. Pin 8.6.2 (2026-10-25); 8.7
to 8.9 are under two weeks old. GridStack (MIT, no dependencies; 14.0.0, 2026-09-21) is the candidate for a
free-form widget grid inside the dashboard panel if Dockview's grid is not enough. Golden Layout (MIT) is set
aside: its last release was 2.6.0 in 2022. Plugin UI is plain ES modules, so no framework is imposed; the shell
itself uses none.

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

**Server side (Python).** `register(wb)` may call `wb.content_type(...)`, `wb.extractor(name, fn)`,
`wb.route(path, handler)` (under `/api/plugins/<id>/`), `wb.on(event, fn)` (item and claim changes,
decisions) and `wb.task(name, fn, schedule)`. An extractor is `fn(source, ctx) -> iterable of records`; `ctx`
records the run and writes through the API.

**Client side (ES module).** The default export lists `panels` (each `{id, title, mount(el, ctx)}` returning an
unmount function), `widgets` (dashboard pieces, same shape), `commands` and `menu` entries. `ctx` gives `api`
(the REST client), `open(panelId, params)`, `events` (subscribe to live changes), `user` and `settings`.

**Integrations.** Everything a panel does goes through a JSON HTTP API described by OpenAPI, so other tools can
do the same. An MCP server over the same API lets agents (Claude Code) read and write as a named user. Events
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
- Breaking out means moving `workbench/` to its own repository and cloning it into `repos/`, as kernel and
  Morphogen are.

## 7. Server

Python, because the extractors and resolvers worth reusing are Python (kernel's encoders, Splink):

| Package | Licence | Pin (two weeks or older) |
| --- | --- | --- |
| Starlette | BSD-3-Clause | 1.10.0 (2026-10-24) |
| Uvicorn | BSD-3-Clause | 0.54.0 (2026-09-25) |
| psycopg | LGPL-3.0 (library) | 3.3.6 (2026-09-18) |
| jsonschema | MIT | 4.26.0 (2026-01-07) |

All four are allowed by kernel D-11's posture (permissive, or LGPL as a library).

## 8. Alternatives considered (GitHub, 2026-11-08)

| Project | Licence | Why not as the base |
| --- | --- | --- |
| Payload | MIT | The closest: content types, an admin UI, plugins, auth, Postgres. But it is Next.js and TypeScript end to end, has no claims or provenance layer, and its admin is CRUD screens, not a window manager. Its collection and plugin config are worth borrowing |
| PostgREST | MIT | An API for any Postgres schema. A candidate to serve `content.*` read-only later; it does not do claims, extractors or a UI |
| Supabase | Apache-2.0 | A whole platform (auth, storage, functions); far more than one owner's system needs |
| Directus, Strapi | not plainly permissive (GitHub reports NOASSERTION; Directus set aside in S-39) | fails the licence rule |
| Graphiti | Apache-2.0 | Temporal knowledge graphs for agents, claims-shaped, on Neo4j, FalkorDB or Kuzu, not Postgres |
| Cognee | Apache-2.0 | Memory pipelines for agents; Postgres and pgvector for storage, with the graph elsewhere; claims-shaped |

## 9. Build order

| # | Step | Done when |
| --- | --- | --- |
| W1 | Store, API, sign-in | migrations create `wb.*`; a content type registered from a plugin gets its table; the API creates, edits and lists items, and every write records a claim; `workbench user add owner` and signing in work |
| W2 | Shell and core panels | the sidebar, Dockview window manager, dashboard, content list, item editor with claims beside each field, and review lane run; a layout survives a reload |
| W3 | Plugin loader and Substrate's plugin | `plugins/substrate` loads; its extractors read `catalog-info.yaml` and `.claude/`, and the drift panel shows declared against observed |
| W4 | Kernel leaves the stack | everything Substrate used kernel for runs on Workbench, including Morphogen's verdicts as claims; kernel stops in `deploy/compose.yaml` and becomes an option |

## 10. For the owner

1. **The name.** Workbench is a placeholder.
2. **Roles.** One owner, plus optional editors and viewers, without per-scope clearance. Kernel's clearance
   could return as a plugin if more than one organisation shares a store.
3. **Kernel.** Parked from now on. It leaves the stack at W4, once Workbench does everything Substrate used it
   for. kernel#113 stays a draft.
