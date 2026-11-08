-- Workbench core: the store, the rules and the API's own functions (BRIEF.md sections 2 and 7).
-- Run once, as a superuser, in the workbench database, by `workbench migrate`. The roles exist before it runs
-- (wb_authenticator, wb_anon, wb_viewer, wb_editor, wb_owner; cli.py creates them, since they belong to the
-- whole server).
--
--   wb          the system's own tables
--   content     one table per content type (types.py creates them)
--   api         what PostgREST exposes: a view per content type, the claims, and functions (/rpc/<name>)
--   wb_private  sign-in data nothing outside a security-definer function may read
--   wb_crypto   pgcrypto and the vendored JWT signing (002_jwt.sql)

create schema wb;
create schema content;
create schema api;
create schema wb_private;
create schema wb_crypto;
create extension if not exists pgcrypto schema wb_crypto;
create extension if not exists vector;

revoke all on schema wb, content, api, wb_private, wb_crypto from public;

-- ------------------------------------------------------------------ registry
create table wb.plugin (
  id         text primary key check (id ~ '^[a-z][a-z0-9_-]{0,62}$'),
  version    text not null,
  path       text,
  loaded_at  timestamptz not null default now()
);

create table wb.content_type (
  id          text primary key check (id ~ '^[a-z][a-z0-9_]{0,62}$'),
  plugin      text references wb.plugin(id),
  label       text not null,
  schema      jsonb not null,           -- the JSON Schema it was registered with
  version     integer not null default 1,
  updated_at  timestamptz not null default now()
);

-- ------------------------------------------------------------------ what was read, and by what
create table wb.source (
  id            uuid primary key default gen_random_uuid(),
  uri           text not null,
  sha256        text,
  media_type    text,
  retrieved_at  timestamptz not null default now(),
  location      text                    -- where the bytes are kept, if they are
);
create unique index source_uri_sha on wb.source (uri, coalesce(sha256, ''));

create table wb.run (
  id          uuid primary key default gen_random_uuid(),
  extractor   text not null,
  plugin      text references wb.plugin(id),
  version     text,
  inputs      jsonb not null default '{}',
  started_at  timestamptz not null default now(),
  ended_at    timestamptz,
  outcome     jsonb
);

-- ------------------------------------------------------------------ the evidence layer
create table wb.claim (
  id             uuid primary key default gen_random_uuid(),
  subject_type   text not null,
  subject_id     uuid not null,
  field          text not null,          -- a field of the subject's type, or a relation's predicate
  value          jsonb,                  -- the value as stated (null for a relation)
  object_type    text,                   -- for a relation: what it points at
  object_id      uuid,
  source_id      uuid references wb.source(id),
  quote          text,
  span           jsonb,                  -- where in the source: lines, characters, a time range
  run_id         uuid references wb.run(id),
  author         text,                   -- the signed-in person, or the extractor's name
  observed_at    timestamptz not null default now(),
  valid_from     timestamptz,
  valid_to       timestamptz,
  status         text not null default 'current'
                 check (status in ('current', 'superseded', 'retracted', 'disputed')),
  superseded_by  uuid references wb.claim(id),
  confidence     real check (confidence between 0 and 1),
  hash           text not null           -- same subject, field, value and origin: the same claim
);
create unique index claim_current_hash on wb.claim (hash) where status = 'current';
create index claim_subject on wb.claim (subject_type, subject_id, field);

create table wb.relation (
  id          uuid primary key default gen_random_uuid(),
  from_type   text not null,
  from_id     uuid not null,
  predicate   text not null,
  to_type     text not null,
  to_id       uuid not null,
  created_at  timestamptz not null default now(),
  unique (from_type, from_id, predicate, to_type, to_id)
);

-- ------------------------------------------------------------------ vocabularies and their mappings (SSSOM)
create table wb.term (
  iri         text primary key,
  label       text,
  kind        text check (kind in ('class', 'property', 'value')),
  vocabulary  text
);

create table wb.mapping (                -- column names as SSSOM's mapping slots
  id                     uuid primary key default gen_random_uuid(),
  subject_id             text not null,
  predicate_id           text not null,  -- skos:exactMatch, skos:closeMatch, ...
  object_id              text not null,
  mapping_justification  text not null,  -- a semapv term, e.g. semapv:ManualMappingCuration
  confidence             real check (confidence between 0 and 1),
  author_id              text,
  mapping_set_id         text,
  created_at             timestamptz not null default now(),
  unique (subject_id, predicate_id, object_id, mapping_set_id)
);

-- ------------------------------------------------------------------ decisions (the review lane)
create table wb.decision (
  id          uuid primary key default gen_random_uuid(),
  kind        text not null,             -- gap, dispute, merge, proposal
  subject     jsonb not null,            -- what it is about
  evidence    jsonb not null default '[]',
  status      text not null default 'open' check (status in ('open', 'approved', 'declined')),
  decided_by  text,
  decided_at  timestamptz,
  note        text,
  created_at  timestamptz not null default now()
);

create table wb.embedding (
  id            uuid primary key default gen_random_uuid(),
  subject_type  text not null,
  subject_id    uuid not null,
  model         text not null,
  embedding     vector not null,
  created_at    timestamptz not null default now(),
  unique (subject_type, subject_id, model)
);

-- ------------------------------------------------------------------ people
create table wb_private.person (
  name        text primary key check (name ~ '^[a-z][a-z0-9_.-]{0,62}$'),
  pass        text not null,             -- crypt(), bcrypt
  role        text not null check (role in ('wb_owner', 'wb_editor', 'wb_viewer')),
  disabled    boolean not null default false,
  created_at  timestamptz not null default now()
);

create table wb_private.setting (
  key    text primary key,
  value  text not null
);

-- ------------------------------------------------------------------ the rules every write goes through
-- Who is writing: the signed-in person (PostgREST puts the JWT's claims in request.jwt.claims), else an
-- extractor's name set for the transaction (wb.author), else the database user.
create function wb.author() returns text language sql stable as $$
  select coalesce(nullif(current_setting('request.jwt.claims', true), '')::json ->> 'name',
                  nullif(current_setting('wb.author', true), ''),
                  session_user::text)
$$;

create function wb.current_run() returns uuid language sql stable as $$
  select nullif(current_setting('wb.run', true), '')::uuid
$$;

-- Before a write: who made the item and who changed it last.
create function wb.touch() returns trigger language plpgsql as $$
begin
  if tg_op = 'INSERT' then
    new.created_at := now();
    new.created_by := wb.author();
  else
    new.id := old.id;                    -- an item keeps its identity
    new.created_at := old.created_at;
    new.created_by := old.created_by;
  end if;
  new.updated_at := now();
  new.updated_by := wb.author();
  return new;
end $$;

-- After a write: one claim per field that was set or changed, attributed to whoever wrote it. The same
-- author's earlier current claim about that field is superseded by the new one; other authors' claims stay,
-- so differing sources sit side by side. Runs as its owner, because no API role may write claims directly.
create function wb.record_claims() returns trigger language plpgsql security definer
set search_path = pg_catalog, wb as $$
declare
  who   text := wb.author();
  run   uuid := wb.current_run();
  newj  jsonb := to_jsonb(new);
  oldj  jsonb := case when tg_op = 'UPDATE' then to_jsonb(old) else '{}'::jsonb end;
  k     text;
  v     jsonb;
  cid   uuid;
begin
  for k, v in select key, value from jsonb_each(newj)
              where key not in ('id', 'created_at', 'updated_at', 'created_by', 'updated_by') loop
    continue when tg_op = 'INSERT' and v = 'null'::jsonb;
    continue when tg_op = 'UPDATE' and v is not distinct from oldj -> k;
    cid := null;
    insert into wb.claim (subject_type, subject_id, field, value, author, run_id, hash)
    values (tg_table_name, new.id, k, v, who, run,
            md5(concat_ws('|', tg_table_name, new.id, k, v::text, who, run)))
    on conflict (hash) where status = 'current' do nothing
    returning id into cid;
    if cid is not null then
      update wb.claim set status = 'superseded', superseded_by = cid
      where subject_type = tg_table_name and subject_id = new.id and field = k and status = 'current'
        and id <> cid and author is not distinct from who;
    end if;
  end loop;
  return null;
end $$;

-- ------------------------------------------------------------------ the API's own views and functions
create view api.content_types with (security_invoker = true) as
  select id, plugin, label, schema, version, updated_at from wb.content_type;

create view api.claims with (security_invoker = true) as
  select id, subject_type, subject_id, field, value, object_type, object_id, source_id, quote, span, run_id,
         author, observed_at, valid_from, valid_to, status, superseded_by, confidence
  from wb.claim;

-- Sign in: name and password in, a JWT out (PostgREST's SQL user management pattern, v16.5 docs).
create function api.login(name text, pass text) returns json language plpgsql security definer
set search_path = pg_catalog, wb_private, wb_crypto as $$
declare
  r       text;
  secret  text;
begin
  select p.role into r from wb_private.person p
  where p.name = login.name and not p.disabled and p.pass = wb_crypto.crypt(login.pass, p.pass);
  if r is null then
    perform pg_sleep(1);                 -- slows guessing
    raise invalid_password using message = 'name or password not accepted';
  end if;
  select value into secret from wb_private.setting where key = 'jwt_secret';
  return json_build_object(
    'token', wb_crypto.sign(json_build_object('role', r, 'name', login.name,
                                              'exp', extract(epoch from now() + interval '8 hours')::bigint),
                            secret),
    'name', login.name, 'role', r);
end $$;

create function api.whoami() returns json language sql stable as $$
  select json_build_object('name', wb.author(), 'role', current_user)
$$;

revoke execute on all functions in schema api, wb, wb_private, wb_crypto from public;

-- ------------------------------------------------------------------ grants (per content type: types.py)
grant usage on schema api to wb_anon, wb_viewer;
grant usage on schema content, wb to wb_viewer;
grant execute on function api.login(text, text) to wb_anon, wb_viewer;
grant execute on function api.whoami() to wb_viewer;
grant execute on function wb.author(), wb.current_run() to wb_viewer;
grant select on wb.content_type, wb.claim to wb_viewer;
grant select on api.content_types, api.claims to wb_viewer;

comment on schema api is 'Workbench: content types, items and the claims behind every value.';
