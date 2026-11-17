-- The store (S-135): Wikibase's data model in Postgres, with OpenWiki's pinned evidence.
--
--   entity      an item (Q1) or a property (P1, with a datatype): label, description, aliases, prose
--   statement   subject, property, a typed value, a rank; its value is fixed once written (a new belief is a
--               new statement, the old one deprecated); qualifiers in store.qualifier
--   reference   who stated it (a parser's run, an interpreter and its version, a person, a rule and its
--               premises) and the span it rests on; shared, write-once; store.cites links it to statements
--   source/span a source cut into spans (paragraphs, line ranges), each a pinned text with its hash. A new read
--               with different text supersedes the span and keeps the old one, so what was cited stays readable
--   revision    one row per entity per transaction that touched it, with who (store.actor) and a snapshot
--
-- Derived, never stored: store.usable (Wikidata's best rank: preferred if any, else normal), store.flag
-- (statements resting on a superseded span, and everything derived from them, by rule premises; no model
-- call), store.violation (constraints, which are statements on properties, reported and never blocking).
-- store.page caches each entity's rendered page for search; store.render() is always current.

-- No JIT here: the planner overestimates the recursive views (store.flag) by orders of magnitude, and compiling
-- for each of a page's statements cost half a second a write; the store's queries are small.
do $$ begin execute format('alter database %I set jit = off', current_database()); end $$;

create extension if not exists pg_trgm;
create extension if not exists vector;
create schema store;

create sequence store.item_number;
create sequence store.property_number;

-- Entities -----------------------------------------------------------------------------------------------

create table store.entity (
  id          text primary key check (id ~ '^[QP][1-9][0-9]*$'),
  kind        text not null generated always as (case left(id, 1) when 'Q' then 'item' else 'property' end) stored,
  datatype    text check (datatype in ('item', 'property', 'string', 'quantity', 'time', 'coordinate', 'url', 'external-id')),
  key         text unique check (key ~ '^[a-z0-9][a-z0-9:._/-]*$'),   -- a stable name code and imports find it by
  label       text not null check (label <> ''),
  description text,
  aliases     text[] not null default '{}',
  prose       text,                                                     -- the page's own words, beside its statements
  created_at  timestamptz not null default now(),
  check ((left(id, 1) = 'P') = (datatype is not null))
);
create index entity_label_trgm on store.entity using gin (label gin_trgm_ops);

create function store.key(p_key text) returns text language sql stable as
  $$ select id from store.entity where key = p_key $$;

create function store.new_entity(p_kind text, p_label text, p_key text default null, p_description text default null,
                                 p_datatype text default null, p_aliases text[] default '{}', p_prose text default null)
returns text language plpgsql as $$
declare nid text;
begin
  if p_key is not null then
    select id into nid from store.entity where key = p_key;
    if found then return nid; end if;
  end if;
  nid := case p_kind when 'item' then 'Q' || nextval('store.item_number')
                     when 'property' then 'P' || nextval('store.property_number') end;
  if nid is null then raise exception 'store: an entity is an item or a property, not %', p_kind; end if;
  insert into store.entity (id, key, label, description, datatype, aliases, prose)
  values (nid, p_key, p_label, p_description, p_datatype, coalesce(p_aliases, '{}'), p_prose);
  return nid;
end $$;

-- Sources and spans --------------------------------------------------------------------------------------

create table store.source (
  id          uuid primary key default gen_random_uuid(),
  uri         text not null unique,
  media_type  text,
  created_at  timestamptz not null default now()
);

create table store.span (
  id            uuid primary key default gen_random_uuid(),
  source_id     uuid not null references store.source,
  locator       text not null check (locator <> ''),     -- p3, L10-20: where in the source
  text          text not null,
  hash          text not null,                           -- sha256 of text, set on insert
  read_at       timestamptz not null default now(),
  superseded_at timestamptz,                             -- a later read found other text here, or none
  embedding     vector                                   -- filled once an embedding model is chosen
);
create unique index span_current on store.span (source_id, locator) where superseded_at is null;

create function store.sha256(p text) returns text language sql immutable as
  $$ select encode(sha256(convert_to(p, 'UTF8')), 'hex') $$;

create function store.span_guard() returns trigger language plpgsql as $$
begin
  if tg_op = 'INSERT' then
    new.hash := store.sha256(new.text);
    return new;
  elsif tg_op = 'UPDATE' then
    if (new.id, new.source_id, new.locator, new.text, new.hash, new.read_at)
       is distinct from (old.id, old.source_id, old.locator, old.text, old.hash, old.read_at)
       or (old.superseded_at is not null and new.superseded_at is distinct from old.superseded_at) then
      raise exception 'store: a span is pinned; a new read of its source makes a new span';
    end if;
    return new;
  end if;
  raise exception 'store: spans are kept, so what cited them stays readable';
end $$;
create trigger span_guard before insert or update or delete on store.span
  for each row execute function store.span_guard();

-- Read a source as a whole: [{locator, text}]. Unchanged spans are kept, changed ones superseded by new spans,
-- and current spans this read did not return are superseded as gone.
create function store.read_source(p_uri text, p_media_type text, p_spans jsonb)
returns table (loc text, span_id uuid, change text) language plpgsql as $$
declare src uuid; sp record; cur record;
begin
  insert into store.source (uri, media_type) values (p_uri, p_media_type)
  on conflict (uri) do update set media_type = coalesce(excluded.media_type, store.source.media_type)
  returning id into src;
  for sp in select x->>'locator' as l, x->>'text' as t from jsonb_array_elements(p_spans) x loop
    select s.id, s.hash into cur from store.span s where s.source_id = src and s.locator = sp.l and s.superseded_at is null;
    if found and cur.hash = store.sha256(sp.t) then
      loc := sp.l; span_id := cur.id; change := 'same'; return next;
      continue;
    end if;
    if found then
      update store.span s set superseded_at = now() where s.id = cur.id;
      change := 'changed';
    else
      change := 'new';
    end if;
    insert into store.span (source_id, locator, text) values (src, sp.l, sp.t) returning id into span_id;
    loc := sp.l; return next;
  end loop;
  for cur in update store.span s set superseded_at = now()
             where s.source_id = src and s.superseded_at is null
               and s.locator not in (select x->>'locator' from jsonb_array_elements(p_spans) x)
             returning s.id, s.locator loop
    loc := cur.locator; span_id := cur.id; change := 'gone'; return next;
  end loop;
end $$;

-- Statements and qualifiers ------------------------------------------------------------------------------

create table store.statement (
  id           uuid primary key default gen_random_uuid(),
  subject      text not null references store.entity,
  property     text not null references store.entity,
  snak         text not null default 'value' check (snak in ('value', 'somevalue', 'novalue')),
  value        jsonb,                                    -- the typed value, for every datatype but item and property
  value_entity text references store.entity,             -- the value, for item and property datatypes
  rank         text not null default 'normal' check (rank in ('preferred', 'normal', 'deprecated')),
  created_at   timestamptz not null default now(),
  check (snak = 'value' or (value is null and value_entity is null)),
  check (value is null or value_entity is null)
);
create index statement_subject on store.statement (subject, property);
create index statement_value_entity on store.statement (value_entity) where value_entity is not null;

create table store.qualifier (
  statement_id uuid not null references store.statement,
  ord          int not null,
  property     text not null references store.entity,
  snak         text not null default 'value' check (snak in ('value', 'somevalue', 'novalue')),
  value        jsonb,
  value_entity text references store.entity,
  primary key (statement_id, ord),
  check (snak = 'value' or (value is null and value_entity is null)),
  check (value is null or value_entity is null)
);

-- A value fits its property's datatype, or the write fails: typed values are what keep the store computable.
create function store.check_value(p_property text, p_snak text, p_value jsonb, p_entity text)
returns void language plpgsql stable as $$
declare dt text; t text; k text; s text;
begin
  select datatype into dt from store.entity where id = p_property;
  if dt is null then raise exception 'store: % is not a property', p_property; end if;
  if p_snak <> 'value' then return; end if;
  if dt in ('item', 'property') then
    if p_entity is null or p_value is not null or left(p_entity, 1) <> (case dt when 'item' then 'Q' else 'P' end) then
      raise exception 'store: % takes an entity (%) as its value', p_property, dt;
    end if;
    return;
  end if;
  if p_entity is not null or p_value is null then
    raise exception 'store: % takes a % value, not an entity', p_property, dt;
  end if;
  t := jsonb_typeof(p_value);
  if dt in ('string', 'external-id', 'url') then
    if t <> 'string' or p_value #>> '{}' = '' then
      raise exception 'store: % takes a non-empty string (%)', p_property, dt;
    end if;
    if dt = 'url' and (p_value #>> '{}') !~ '^[A-Za-z][A-Za-z0-9+.-]*:\S+$' then
      raise exception 'store: % takes a URL, not %', p_property, p_value;
    end if;
    return;
  end if;
  if t <> 'object' then raise exception 'store: % takes a % object, not %', p_property, dt, p_value; end if;
  if dt = 'quantity' then
    for k in select jsonb_object_keys(p_value) loop
      if k not in ('amount', 'unit', 'lower', 'upper') then raise exception 'store: a quantity has no field %', k; end if;
    end loop;
    if coalesce(jsonb_typeof(p_value->'amount'), '') <> 'number' then
      raise exception 'store: a quantity needs a numeric amount, not %', p_value;
    end if;
    if p_value ? 'unit' and jsonb_typeof(p_value->'unit') <> 'null'
       and not exists (select 1 from store.entity e where e.id = p_value->>'unit' and e.kind = 'item') then
      raise exception 'store: a quantity''s unit is an item, not %', p_value->'unit';
    end if;
    foreach k in array array['lower', 'upper'] loop
      if p_value ? k then
        if jsonb_typeof(p_value->k) <> 'number' then raise exception 'store: a quantity''s % is a number', k; end if;
        if (k = 'lower' and (p_value->>k)::numeric > (p_value->>'amount')::numeric)
           or (k = 'upper' and (p_value->>k)::numeric < (p_value->>'amount')::numeric) then
          raise exception 'store: a quantity''s bounds hold its amount (%)', p_value;
        end if;
      end if;
    end loop;
  elsif dt = 'time' then
    for k in select jsonb_object_keys(p_value) loop
      if k not in ('time', 'precision') then raise exception 'store: a time has no field %', k; end if;
    end loop;
    s := p_value->>'time';
    if coalesce(jsonb_typeof(p_value->'time'), '') <> 'string'
       or s !~ '^[+-][0-9]{1,16}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$' then
      raise exception 'store: a time is like +2026-11-17T00:00:00Z (Wikidata''s form), not %', p_value->'time';
    end if;
    if coalesce(jsonb_typeof(p_value->'precision'), '') <> 'number'
       or (p_value->>'precision') !~ '^[0-9]+$' or (p_value->>'precision')::int > 14 then
      raise exception 'store: a time''s precision is 0 to 14 (9 a year, 11 a day), not %', p_value->'precision';
    end if;
  elsif dt = 'coordinate' then
    for k in select jsonb_object_keys(p_value) loop
      if k not in ('latitude', 'longitude', 'precision') then raise exception 'store: a coordinate has no field %', k; end if;
    end loop;
    if coalesce(jsonb_typeof(p_value->'latitude'), '') <> 'number' or coalesce(jsonb_typeof(p_value->'longitude'), '') <> 'number'
       or (p_value ? 'precision' and jsonb_typeof(p_value->'precision') <> 'number') then
      raise exception 'store: a coordinate has numeric latitude and longitude, not %', p_value;
    end if;
    if abs((p_value->>'latitude')::numeric) > 90 or abs((p_value->>'longitude')::numeric) > 180 then
      raise exception 'store: a coordinate is out of range (%)', p_value;
    end if;
  end if;
end $$;

create function store.statement_guard() returns trigger language plpgsql as $$
begin
  if tg_op = 'INSERT' then
    perform store.check_value(new.property, new.snak, new.value, new.value_entity);
    if (select kind from store.entity where id = new.property) <> 'property' then
      raise exception 'store: % is not a property', new.property;
    end if;
    return new;
  elsif tg_op = 'UPDATE' then
    if (new.id, new.subject, new.property, new.snak, new.value, new.value_entity, new.created_at)
       is distinct from (old.id, old.subject, old.property, old.snak, old.value, old.value_entity, old.created_at) then
      raise exception 'store: a statement''s value is fixed; add a new statement and deprecate this one';
    end if;
    return new;
  end if;
  raise exception 'store: statements are deprecated, not deleted';
end $$;
create trigger statement_guard before insert or update or delete on store.statement
  for each row execute function store.statement_guard();

create function store.qualifier_guard() returns trigger language plpgsql as $$
begin
  if tg_op = 'INSERT' then
    perform store.check_value(new.property, new.snak, new.value, new.value_entity);
    return new;
  end if;
  raise exception 'store: qualifiers are part of their statement and fixed with it';
end $$;
create trigger qualifier_guard before insert or update or delete on store.qualifier
  for each row execute function store.qualifier_guard();

create function store.entity_guard() returns trigger language plpgsql as $$
begin
  if tg_op = 'UPDATE' then
    if (new.id, new.datatype, new.created_at) is distinct from (old.id, old.datatype, old.created_at)
       or (old.key is not null and new.key is distinct from old.key) then
      raise exception 'store: an entity''s id, key and datatype are fixed';
    end if;
    return new;
  end if;
  raise exception 'store: entities are kept';
end $$;
create trigger entity_guard before update or delete on store.entity
  for each row execute function store.entity_guard();

-- References ---------------------------------------------------------------------------------------------

create table store.reference (
  id          uuid primary key default gen_random_uuid(),
  by_kind     text not null check (by_kind in ('parser', 'interpreter', 'person', 'rule')),
  by_name     text not null check (by_name <> ''),
  by_version  text,                                  -- an interpreter's version
  run         text,                                  -- a parser's run
  span_id     uuid references store.span,
  note        text,
  fingerprint text not null unique,                  -- the same reference is one row, as in Wikibase
  created_at  timestamptz not null default now(),
  check (by_kind <> 'interpreter' or by_version is not null),
  check (by_kind <> 'parser' or run is not null)
);
create index reference_span on store.reference (span_id) where span_id is not null;

create table store.premise (                          -- a rule's reference: the statements it derived from
  reference_id uuid not null references store.reference,
  statement_id uuid not null references store.statement,
  primary key (reference_id, statement_id)
);
create index premise_statement on store.premise (statement_id);

create table store.cites (
  statement_id uuid not null references store.statement,
  reference_id uuid not null references store.reference,
  primary key (statement_id, reference_id)
);
create index cites_reference on store.cites (reference_id);

create function store.write_once() returns trigger language plpgsql as $$
begin raise exception 'store: % rows are written once', tg_table_name; end $$;
create trigger reference_write_once before update or delete on store.reference
  for each row execute function store.write_once();
create trigger premise_write_once before update or delete on store.premise
  for each row execute function store.write_once();

-- Find or make a reference and cite it from a statement. A rule's reference names its premises, and only a
-- rule's does.
create function store.cite(p_statement uuid, p_kind text, p_name text, p_version text default null, p_run text default null,
                           p_span uuid default null, p_premises uuid[] default '{}', p_note text default null)
returns uuid language plpgsql as $$
declare fp text; rid uuid;
begin
  p_premises := coalesce(p_premises, '{}');
  if (p_kind = 'rule') <> (cardinality(p_premises) > 0) then
    raise exception 'store: a rule''s reference names its premises, and only a rule''s does';
  end if;
  if p_statement = any (p_premises) then raise exception 'store: a statement is not its own premise'; end if;
  fp := store.sha256(jsonb_build_array(p_kind, p_name, p_version, p_run, p_span, p_note,
          (select coalesce(jsonb_agg(x order by x), '[]') from unnest(p_premises) x))::text);
  insert into store.reference (by_kind, by_name, by_version, run, span_id, note, fingerprint)
  values (p_kind, p_name, p_version, p_run, p_span, p_note, fp)
  on conflict (fingerprint) do nothing returning id into rid;
  if rid is null then
    select id into rid from store.reference where fingerprint = fp;
  else
    insert into store.premise select rid, unnest(p_premises);
  end if;
  insert into store.cites values (p_statement, rid) on conflict do nothing;
  return rid;
end $$;

-- Every statement says who stated it: checked at commit, so a statement and its reference go in together.
create function store.statement_cited() returns trigger language plpgsql as $$
begin
  if not exists (select 1 from store.cites where statement_id = new.id) then
    raise exception 'store: statement % (% on %) has no reference; say who stated it', new.id, new.property, new.subject;
  end if;
  return null;
end $$;
create constraint trigger statement_cited after insert on store.statement deferrable initially deferred
  for each row execute function store.statement_cited();

-- Derived views ------------------------------------------------------------------------------------------

create view store.usable as
  select s.* from store.statement s
  where s.rank = 'preferred'
     or (s.rank = 'normal' and not exists (
           select 1 from store.statement p where p.subject = s.subject and p.property = s.property and p.rank = 'preferred'));

-- What a changed span puts in doubt: the statements citing it, then everything derived from those.
create view store.flag as
  with recursive f (statement_id, span_id, via) as (
    select c.statement_id, s.id, null::uuid
    from store.span s join store.reference r on r.span_id = s.id join store.cites c on c.reference_id = r.id
    where s.superseded_at is not null
    union
    select c.statement_id, f.span_id, f.statement_id
    from f join store.premise p on p.statement_id = f.statement_id join store.cites c on c.reference_id = p.reference_id
  )
  select distinct f.statement_id, f.span_id, f.via,
         case when f.via is not null then 'derived from a flagged statement'
              when exists (select 1 from store.span n where n.source_id = s.source_id and n.locator = s.locator and n.superseded_at is null)
              then 'its span changed' else 'its span is gone' end as reason
  from f join store.span s on s.id = f.span_id;

create function store.is_instance(p_item text, p_class text) returns boolean language sql stable as $$
  with recursive up (cls) as (
    select u.value_entity from store.usable u where u.subject = p_item and u.property = store.key('instance-of')
    union
    select u.value_entity from store.usable u join up on u.subject = up.cls where u.property = store.key('subclass-of')
  )
  select exists (select 1 from up where cls = p_class) $$;

-- Constraints are statements on properties (property-constraint), with their parameters as qualifiers.
create view store.violation as
  with c as (
    select s.id as constraint_id, s.subject as property, k.key as kind
    from store.usable s join store.entity k on k.id = s.value_entity
    where s.property = store.key('property-constraint')
  )
  select x.statement_id, x.subject, x.property, x.constraint_id, x.kind, x.message from (
    select u.id as statement_id, u.subject, u.property, c.constraint_id, 'single-value'::text as kind,
           format('%s has %s usable values for %s; it takes one', u.subject, count(*) over (partition by u.subject, u.property, c.constraint_id), u.property) as message,
           count(*) over (partition by u.subject, u.property, c.constraint_id) as n
    from store.usable u join c on c.property = u.property and c.kind = 'single-value-constraint'
  ) x where x.n > 1
  union all
  select u.id, u.subject, u.property, c.constraint_id, 'format',
         format('%s does not match the format %s', u.value, q.value #>> '{}')
  from store.usable u join c on c.property = u.property and c.kind = 'format-constraint'
       join store.qualifier q on q.statement_id = c.constraint_id and q.property = store.key('format-as-regex')
  where jsonb_typeof(u.value) = 'string' and (u.value #>> '{}') !~ ('^(?:' || (q.value #>> '{}') || ')$')
  union all
  select u.id, u.subject, u.property, c.constraint_id, 'one-of',
         format('%s is not one of the values %s allows', u.value_entity, u.property)
  from store.usable u join c on c.property = u.property and c.kind = 'one-of-constraint'
  where u.value_entity is not null and not exists (
    select 1 from store.qualifier q where q.statement_id = c.constraint_id
      and q.property = store.key('item-of-property-constraint') and q.value_entity = u.value_entity)
  union all
  select u.id, u.subject, u.property, c.constraint_id, 'value-type',
         format('%s is not an instance of a class %s allows', u.value_entity, u.property)
  from store.usable u join c on c.property = u.property and c.kind = 'value-type-constraint'
  where u.value_entity is not null and not exists (
    select 1 from store.qualifier q where q.statement_id = c.constraint_id
      and q.property = store.key('class') and store.is_instance(u.value_entity, q.value_entity));

-- Pages --------------------------------------------------------------------------------------------------

create function store.fmt(p_property text, p_snak text, p_value jsonb, p_entity text) returns text
language plpgsql stable as $$
declare dt text; t text; p int; r text;
begin
  if p_snak = 'somevalue' then return 'unknown value'; end if;
  if p_snak = 'novalue' then return 'no value'; end if;
  if p_entity is not null then
    return (select format('%s (%s)', label, id) from store.entity where id = p_entity);
  end if;
  select datatype into dt from store.entity where id = p_property;
  if dt = 'quantity' then
    r := p_value->>'amount';
    if p_value ? 'lower' or p_value ? 'upper' then
      r := r || format(' [%s to %s]', coalesce(p_value->>'lower', '?'), coalesce(p_value->>'upper', '?'));
    end if;
    if p_value->>'unit' is not null then
      r := r || ' ' || coalesce((select label from store.entity where id = p_value->>'unit'), p_value->>'unit');
    end if;
    return r;
  elsif dt = 'time' then
    t := ltrim(p_value->>'time', '+'); p := (p_value->>'precision')::int;
    return case when p >= 14 then replace(rtrim(t, 'Z'), 'T', ' ')
                when p >= 11 then split_part(t, 'T', 1)
                when p = 10 then left(split_part(t, 'T', 1), -3)
                when p = 9 then split_part(t, '-', 1) || case when left(p_value->>'time', 1) = '-' then ' BCE' else '' end
                else format('%s (precision %s)', split_part(t, '-', 1), p) end;
  elsif dt = 'coordinate' then
    return format('%s, %s', p_value->>'latitude', p_value->>'longitude');
  elsif dt = 'url' then
    return '<' || (p_value #>> '{}') || '>';
  elsif dt = 'external-id' then
    return '`' || (p_value #>> '{}') || '`';
  end if;
  return p_value #>> '{}';
end $$;

-- One line about a statement: subject, property, value.
create function store.gloss(p_statement uuid) returns text language sql stable as $$
  select format('%s %s %s', e.label, p.label, store.fmt(s.property, s.snak, s.value, s.value_entity))
  from store.statement s join store.entity e on e.id = s.subject join store.entity p on p.id = s.property
  where s.id = p_statement $$;

create function store.fmt_reference(p_reference uuid) returns text language sql stable as $$
  select concat_ws(' ',
    format('%s %s', r.by_kind, r.by_name),
    case when r.by_version is not null then format('(version %s)', r.by_version) end,
    case when r.run is not null then format('(run %s)', r.run) end,
    case when r.span_id is not null then (
      select format('in %s at %s: "%s"%s', so.uri, sp.locator,
                    case when length(sp.text) > 160 then left(sp.text, 157) || '...' else sp.text end,
                    case when sp.superseded_at is not null then ' (changed since it was cited)' else '' end)
      from store.span sp join store.source so on so.id = sp.source_id where sp.id = r.span_id) end,
    case when r.by_kind = 'rule' then (
      select 'from: ' || string_agg(store.gloss(pr.statement_id), '; ' order by pr.statement_id)
      from store.premise pr where pr.reference_id = r.id) end,
    case when r.note is not null then format('(%s)', r.note) end)
  from store.reference r where r.id = p_reference $$;

-- The page people and agents read: the entity's usable statements (all of them with p_all_ranks), qualifiers,
-- numbered references, and what is flagged.
create function store.render(p_id text, p_all_ranks boolean default false) returns text
language plpgsql stable set jit = off as $$
declare e store.entity; out text; r record; q record; ref uuid; refs uuid[] := '{}'; n int; marks text; prev text; hidden int; why text;
begin
  select * into e from store.entity where id = p_id;
  if not found then return null; end if;
  out := format(E'# %s (%s)\n', e.label, e.id);
  if e.description is not null then out := out || E'\n' || e.description || E'\n'; end if;
  if e.datatype is not null then out := out || format(E'\nA property; its values are of type %s.\n', e.datatype); end if;
  if cardinality(e.aliases) > 0 then out := out || E'\nAlso known as: ' || array_to_string(e.aliases, ', ') || E'\n'; end if;
  if e.prose is not null then out := out || E'\n' || e.prose || E'\n'; end if;
  for r in
    select s.*, p.label as plabel from store.statement s join store.entity p on p.id = s.property
    where s.subject = p_id and (p_all_ranks or s.id in (select u.id from store.usable u where u.subject = p_id))
    order by p.label, s.property, s.created_at, s.id
  loop
    if prev is null then out := out || E'\n## Statements\n'; end if;
    if r.property is distinct from prev then out := out || format(E'\n**%s** (%s)\n', r.plabel, r.property); prev := r.property; end if;
    marks := '';
    for ref in select c.reference_id from store.cites c join store.reference x on x.id = c.reference_id
               where c.statement_id = r.id order by x.created_at, x.id loop
      n := array_position(refs, ref);
      if n is null then refs := refs || ref; n := cardinality(refs); end if;
      marks := marks || format('[%s]', n);
    end loop;
    select string_agg(distinct f.reason, '; ') into why from store.flag f where f.statement_id = r.id;
    out := out || format(E'- %s%s%s%s\n', replace(store.fmt(r.property, r.snak, r.value, r.value_entity), E'\n', E'\n  '),
                         case when r.rank <> 'normal' then format(' (%s)', r.rank) else '' end,
                         case when marks <> '' then ' ' || marks else '' end,
                         case when why is not null then format(' **flagged: %s**', why) else '' end);
    for q in select qq.*, p.label as plabel from store.qualifier qq join store.entity p on p.id = qq.property
             where qq.statement_id = r.id order by qq.ord loop
      out := out || format(E'  - %s: %s\n', q.plabel, replace(store.fmt(q.property, q.snak, q.value, q.value_entity), E'\n', E'\n    '));
    end loop;
  end loop;
  if not p_all_ranks then
    select count(*) into hidden from store.statement s where s.subject = p_id
      and s.id not in (select u.id from store.usable u where u.subject = p_id);
    if hidden > 0 then
      out := out || format(E'\n%s statement(s) at a lower rank are not shown (read with all ranks to see them).\n', hidden);
    end if;
  end if;
  if cardinality(refs) > 0 then
    out := out || E'\n## References\n\n';
    for n in 1 .. cardinality(refs) loop
      out := out || format(E'%s. %s\n', n, store.fmt_reference(refs[n]));
    end loop;
  end if;
  return out;
end $$;

create table store.page (
  entity_id   text primary key references store.entity,
  markdown    text not null,
  tsv         tsvector generated always as (to_tsvector('simple', markdown)) stored,
  rendered_at timestamptz not null default now(),
  embedding   vector                                  -- of markdown; filled once an embedding model is chosen
);
create index page_tsv on store.page using gin (tsv);

create function store.search(p_query text, p_limit int default 10)
returns table (id text, label text, description text, score real) language sql stable as $$
  select e.id, e.label, e.description,
         greatest(similarity(e.label, p_query),
                  coalesce((select max(similarity(a, p_query)) from unnest(e.aliases) a), 0),
                  coalesce(ts_rank(pg.tsv, websearch_to_tsquery('simple', p_query)), 0))::real as score
  from store.entity e left join store.page pg on pg.entity_id = e.id
  where e.id = upper(p_query) or e.key = p_query or e.label % p_query or e.label ilike '%' || p_query || '%'
     or exists (select 1 from unnest(e.aliases) a where a ilike '%' || p_query || '%')
     or pg.tsv @@ websearch_to_tsquery('simple', p_query)
  order by (e.id = upper(p_query) or e.key = p_query) desc, score desc, e.id
  limit p_limit $$;

-- Revisions ----------------------------------------------------------------------------------------------

create table store.revision (
  id        bigserial primary key,
  entity_id text not null references store.entity,
  txid      xid8 not null default pg_current_xact_id(),
  at        timestamptz not null default now(),
  by        text not null,
  summary   text,
  snapshot  jsonb not null,
  unique (entity_id, txid)
);

create function store.snapshot(p_id text) returns jsonb language sql stable as $$
  select jsonb_build_object('id', e.id, 'key', e.key, 'label', e.label, 'description', e.description,
    'aliases', e.aliases, 'prose', e.prose, 'datatype', e.datatype,
    'statements', coalesce((
      select jsonb_agg(jsonb_build_object('id', s.id, 'property', s.property, 'snak', s.snak, 'value', s.value,
               'value_entity', s.value_entity, 'rank', s.rank,
               'qualifiers', coalesce((select jsonb_agg(jsonb_build_object('property', q.property, 'snak', q.snak,
                               'value', q.value, 'value_entity', q.value_entity) order by q.ord)
                             from store.qualifier q where q.statement_id = s.id), '[]'),
               'references', coalesce((select jsonb_agg(c.reference_id order by c.reference_id)
                             from store.cites c where c.statement_id = s.id), '[]'))
             order by s.created_at, s.id)
      from store.statement s where s.subject = e.id), '[]'))
  from store.entity e where e.id = p_id $$;

-- One revision per entity per transaction, by whoever set store.actor; the page is re-rendered with it.
create function store.touch(p_id text) returns void language plpgsql set jit = off as $$
declare actor text := nullif(current_setting('store.actor', true), '');
begin
  if actor is null then
    raise exception 'store: say who is editing first (set store.actor), so the revision names them';
  end if;
  insert into store.revision (entity_id, by, summary, snapshot)
  values (p_id, actor, nullif(current_setting('store.summary', true), ''), store.snapshot(p_id))
  on conflict (entity_id, txid) do update
    set snapshot = excluded.snapshot, at = now(), summary = coalesce(excluded.summary, store.revision.summary);
  insert into store.page (entity_id, markdown) values (p_id, store.render(p_id))
  on conflict (entity_id) do update set markdown = excluded.markdown, rendered_at = now(), embedding = null;
end $$;

create function store.touch_entity() returns trigger language plpgsql as $$
begin perform store.touch(x.id) from (select distinct id from changed) x; return null; end $$;
create function store.touch_statement() returns trigger language plpgsql as $$
begin perform store.touch(x.subject) from (select distinct subject from changed) x; return null; end $$;
create function store.touch_by_statement() returns trigger language plpgsql as $$
begin
  perform store.touch(x.subject) from (select distinct s.subject from changed c join store.statement s on s.id = c.statement_id) x;
  return null;
end $$;

create trigger entity_revision_ins after insert on store.entity referencing new table as changed
  for each statement execute function store.touch_entity();
create trigger entity_revision_upd after update on store.entity referencing new table as changed
  for each statement execute function store.touch_entity();
create trigger statement_revision_ins after insert on store.statement referencing new table as changed
  for each statement execute function store.touch_statement();
create trigger statement_revision_upd after update on store.statement referencing new table as changed
  for each statement execute function store.touch_statement();
create trigger qualifier_revision after insert on store.qualifier referencing new table as changed
  for each statement execute function store.touch_by_statement();
create trigger cites_revision_ins after insert on store.cites referencing new table as changed
  for each statement execute function store.touch_by_statement();
create trigger cites_revision_del after delete on store.cites referencing old table as changed
  for each statement execute function store.touch_by_statement();

-- The core vocabulary ------------------------------------------------------------------------------------
-- Wikidata's own, by key (its P/Q numbers in the descriptions); ids here are this store's.

select set_config('store.actor', 'store:migration 001', true);
select set_config('store.summary', 'the core vocabulary', true);

select store.new_entity('property', 'instance of', 'instance-of', 'that class of which this subject is a particular example (Wikidata P31)', 'item');
select store.new_entity('property', 'subclass of', 'subclass-of', 'every instance of this subject is an instance of that class (Wikidata P279)', 'item');
select store.new_entity('property', 'property constraint', 'property-constraint', 'a constraint on this property''s use, checked and reported, never blocking (Wikidata P2302)', 'item');
select store.new_entity('property', 'format as a regular expression', 'format-as-regex', 'a format constraint''s pattern, matched against the whole value (Wikidata P1793)', 'string');
select store.new_entity('property', 'class', 'class', 'a value-type constraint''s allowed class (Wikidata P2308)', 'item');
select store.new_entity('property', 'item of property constraint', 'item-of-property-constraint', 'a one-of constraint''s allowed value (Wikidata P2305)', 'item');
select store.new_entity('property', 'reason for deprecated rank', 'reason-for-deprecated-rank', 'why a statement was deprecated (Wikidata P2241, a string here)', 'string');
select store.new_entity('item', 'single-value constraint', 'single-value-constraint', 'the property usually has one usable value per subject (Wikidata Q19474404)');
select store.new_entity('item', 'format constraint', 'format-constraint', 'the property''s string values match a pattern (Wikidata Q21502404)');
select store.new_entity('item', 'one-of constraint', 'one-of-constraint', 'the property''s values are among those listed (Wikidata Q21510859)');
select store.new_entity('item', 'value-type constraint', 'value-type-constraint', 'the property''s values are instances of a class (Wikidata Q21510865)');
