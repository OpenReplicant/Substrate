# Workbench

*Working name.* A content system on Postgres: real tables per content type, a claims table beside them so every
value can say where it came from, vocabularies and SSSOM mappings as tables, and plugins that add content types,
extractors and UI panels. [`BRIEF.md`](BRIEF.md) is the design and its build order.

It lives inside Substrate for now and imports nothing from it; it is meant to leave as its own project.

## What runs

```
Caddy ──┬─ /api/*  PostgREST v16.5 ──▶ Postgres: database `workbench` (schemas api, content, wb, wb_private, wb_crypto)
        └─ /       the shell (W2)
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

## Tests

```sh
WORKBENCH_ADMIN_URL=postgresql://postgres:...@127.0.0.1:5432/postgres python3 tests/test_w1.py
```

They run in a throwaway database, which they drop.

## Known limits (W1)

- Disabling a person stops new sign-ins; a token they already hold works until it expires (8 hours).
- Rights are per role, not per item; row-level security per item comes when a plugin needs it.
- Conflicting claims from different authors sit side by side, but nothing marks them `disputed` yet.

## Licence

Apache-2.0. `workbench/sql/002_jwt.sql` is from pgjwt 0.2.0, MIT (`LICENSES/pgjwt-MIT.txt`).
