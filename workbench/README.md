# Workbench

*Working name.* A content system on Postgres: real tables per content type, a claims table beside them so every
value can say where it came from, vocabularies and SSSOM mappings as tables, and plugins that add content types,
extractors and UI panels. [`BRIEF.md`](BRIEF.md) is the design and its build order.

It lives inside Substrate for now and imports nothing from it; it is meant to leave as its own project.

## What runs

```
Caddy ──┬─ /api/*  PostgREST v16.5 ──▶ Postgres: database `workbench` (schemas api, content, wb, wb_private, wb_crypto)
        ├─ /plugins/<id>/web/*   each plugin's browser files (nothing else in a plugin folder is served)
        └─ /       the shell: index.html is a Caddy template that finds the installed plugins
```

The rules are in Postgres (`workbench/sql/`): a trigger records a claim for every field a write sets or
changes, attributed to the signed-in person; an edit supersedes the same author's earlier claim and leaves other
authors' beside it; roles are `wb_viewer` (read), `wb_editor` (add and change), `wb_owner`; nobody deletes, and
nobody writes claims directly. PostgREST serves the `api` schema: one view per content type, `claims`,
`content_types`, and `rpc/login` (name and password in, a JWT out) and `rpc/whoami`.

## Commands

```sh
python3 -m workbench migrate                      # the database, roles and core schema; applies what is new
python3 -m workbench plugin load DIR              # a plugin's content types become tables and API endpoints
python3 -m workbench type add SCHEMA.json [--plugin ID]
python3 -m workbench user add NAME [--role owner|editor|viewer]    # prints the password once
python3 -m workbench user reset NAME | user disable NAME | user list
```

Settings: `WORKBENCH_ADMIN_URL` (a superuser URL for the server), `WORKBENCH_DB` (default `workbench`),
`WORKBENCH_AUTHENTICATOR_PASSWORD` (PostgREST's login), `WORKBENCH_JWT_SECRET` (32 characters or more; PostgREST
gets the same value as `PGRST_JWT_SECRET`). In Substrate, `scripts/workbench.sh` sets them from `.env`.

## Using the API

```sh
curl -X POST http://127.0.0.1:8080/api/rpc/login -H 'Content-Type: application/json' \
     -d '{"name": "owner", "pass": "..."}'                    # {"token": ..., "name": ..., "role": ...}
curl http://127.0.0.1:8080/api/component -H "Authorization: Bearer $TOKEN"
curl "http://127.0.0.1:8080/api/claims?subject_id=eq.$ID" -H "Authorization: Bearer $TOKEN"
curl http://127.0.0.1:8080/api/ -H "Authorization: Bearer $TOKEN"   # the OpenAPI description
```

## A plugin

```yaml
# plugin.yaml
id: my-plugin
version: 0.1.0
licence: Apache-2.0
requires: {workbench: "1"}
content_types: [types/*.json]      # one JSON Schema per type; the file name is the type's id
```

A property's JSON type decides its column (`string` text, with `date-time`, `date` and `uuid` formats; `integer`
bigint; `number` double precision; `boolean`; anything else jsonb). Every type also has `id`, `slug`, `title`,
`created_at`, `updated_at`, `created_by` and `updated_by`. Registering again adds new columns and never drops one.

## The shell

An IDE-shaped desktop: a **sidebar** (where things live; plugins add entries, content types appear under
Content, apps under Apps), a **workspace** of tabs that split, float and pop out (Dockview), an **inspector** for
the current selection (first: where each value came from), a **dashboard** of widget cards, and a **command
palette** (Ctrl/Cmd K) that runs commands and finds items across every type. Alpine.js (its CSP build) drives the
core screens; the page runs under a strict Content-Security-Policy (no inline script or style, no eval).

## Client plugins

A plugin's `web/index.js` default export is called with `wb` before the page starts:

```js
export default function myPlugin(wb) {
  wb.view({id: 'my-view', title: (p) => 'Mine', template: 'my-tpl'});      // a tab; markup in web/views.html
  wb.widget({id: 'my-widget', title: 'Mine', size: 's', mount(el, wb) { el.textContent = 'hi'; return () => {}; }});
  wb.inspector({id: 'my-section', title: 'Mine', applies: (sel) => sel?.type === 'component', template: 'my-insp'});
  wb.field({id: 'colour', match: (prop) => (prop.format === 'color' ? 3 : 0), mount(el, {value, set}) { ... }});
  wb.command({id: 'my-cmd', title: 'Do the thing', run: (wb) => wb.notify('done')});
  wb.menu({id: 'my-menu', section: 'Workspace', title: 'Mine', icon: 'doc', open: ['my-view', {}]});
  wb.app({id: 'grafana', title: 'Grafana', url: '/apps/grafana/', embed: 'frame'});   // or embed: 'window'
  wb.data('myComponent', () => ({ /* an Alpine component for your templates */ }));
}
```

`web/views.html` holds the plugin's `<template id="...">`s; the page includes it at serve time. A view or
widget uses either a `template` (Alpine) or `mount(el, wb)` (anything; return a cleanup function). `wb` also
gives `api` (PostgREST), `open(viewId, params, {where})`, `select({type, id, field})`, `state` (types,
selection), `on(event, fn)` (`saved`, `selection`, `claims-changed`, `signedin`), `notify`, `canEdit()`,
`format` (`ago`, `when`, `show`) and `panelOf(el)` (a view's params and title).

Apps: a web UI that allows framing from Workbench's origin opens as a tab (`embed: 'frame'`; another origin must
be listed in `WB_FRAME_SRC`); one that refuses (`X-Frame-Options`, `frame-ancestors`) opens in its own window
(`embed: 'window'`). Kernel's UI is the second kind.

## Tests

```sh
WORKBENCH_ADMIN_URL=postgresql://postgres:...@127.0.0.1:5432/postgres python3 tests/test_w1.py
```

They run in a throwaway database, which they drop.

## Known limits

- Disabling a person stops new sign-ins; a token they already hold works until it expires (8 hours).
- Rights are per role, not per item; row-level security per item comes when a plugin needs it.
- Conflicting claims from different authors sit side by side, but nothing marks them `disputed` yet; the item
  editor shows "N sources disagree" beside such a field.
- No live updates yet: views reload on their own saves; events from other people arrive with the server (W3).
- Content types are read-only in the UI; a plugin registers them.

## Licence

Apache-2.0. `workbench/sql/002_jwt.sql` is from pgjwt 0.2.0, MIT (`LICENSES/pgjwt-MIT.txt`). `web/vendor/` holds
Alpine.js's CSP build 3.17.5 (MIT) and dockview-core 8.6.2 (MIT; its stylesheet extracted from its UMD build
unchanged), each with its licence.
