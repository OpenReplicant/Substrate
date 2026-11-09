-- Relations are claims too; a conclusion goes with its premises; terms say how they relate; the graph engine.
--
-- 1. A relation an extractor states is recorded as a claim beside it (field = the predicate, object_type and
--    object_id = what it points at), with the run, source, quote and span, as values are. wb.replace_relations
--    is how a run states its relations: it adds what is new and retracts what it no longer states, for the
--    items the run read.
-- 2. A claim may name its premises (span.premises, a list of claim ids), as an inference does. When a claim is
--    retracted, every current claim resting on it is retracted too, and a retracted relation claim takes its
--    relation row with it.
-- 3. Terms gain what a reasoner and a SPARQL endpoint need: parents (rdfs:subClassOf / subPropertyOf),
--    characteristics (transitive, symmetric), an inverse, domain and range, the plugin that loaded them, and
--    for a property the relation predicate it names.
-- 4. pgGraph, for traversal over the same tables as the caller.

-- ------------------------------------------------------------------ 1. relations stated as claims
create or replace function wb.replace_relations(p_scope jsonb, p_rels jsonb) returns integer
language plpgsql security definer set search_path = pg_catalog, wb as $$
declare
  who     text := wb.author();
  run     uuid := wb.current_run();
  r       jsonb;
  hashes  text[] := '{}';
  h       text;
  n       integer;
begin
  for r in select * from jsonb_array_elements(coalesce(p_rels, '[]'::jsonb)) loop
    h := md5(concat_ws('|', 'relation', r->>'from_type', r->>'from_id', r->>'predicate', r->>'to_type', r->>'to_id', who));
    hashes := hashes || h;
    insert into wb.claim (subject_type, subject_id, field, value, object_type, object_id, source_id, quote, span,
                          run_id, author, hash)
    values (r->>'from_type', (r->>'from_id')::uuid, r->>'predicate', null, r->>'to_type', (r->>'to_id')::uuid,
            nullif(r->>'source', '')::uuid, r->>'quote', r->'span', run, who, h)
    on conflict (hash) where status = 'current' do nothing;
    insert into wb.relation (from_type, from_id, predicate, to_type, to_id, author, run, source)
    values (r->>'from_type', (r->>'from_id')::uuid, r->>'predicate', r->>'to_type', (r->>'to_id')::uuid, who, run,
            nullif(r->>'source', '')::uuid)
    on conflict do nothing;
  end loop;
  -- what this author stated before from these items and no longer does
  update wb.claim c set status = 'retracted'
   where c.author is not distinct from who and c.status = 'current' and c.object_id is not null
     and exists (select 1 from jsonb_array_elements(p_scope) s where s->>'type' = c.subject_type and (s->>'id')::uuid = c.subject_id)
     and not (c.hash = any(hashes));
  get diagnostics n = row_count;
  -- relation rows from before relations had claims (no author) go when their item is read again
  delete from wb.relation x
   where (x.author is null or x.author = who)
     and exists (select 1 from jsonb_array_elements(p_scope) s where s->>'type' = x.from_type and (s->>'id')::uuid = x.from_id)
     and not exists (select 1 from jsonb_array_elements(coalesce(p_rels, '[]'::jsonb)) e(rel)
                      where e.rel->>'from_type' = x.from_type and (e.rel->>'from_id')::uuid = x.from_id
                        and e.rel->>'predicate' = x.predicate and e.rel->>'to_type' = x.to_type
                        and (e.rel->>'to_id')::uuid = x.to_id and x.author is not distinct from who);
  return n;
end $$;
revoke execute on function wb.replace_relations(jsonb, jsonb) from public;
grant execute on function wb.replace_relations(jsonb, jsonb) to wb_server;

-- a new value supersedes its author's earlier value for that field, never a relation claim of the same name
create or replace function wb.record_claims() returns trigger language plpgsql security definer
set search_path = pg_catalog, wb as $$
declare
  who       text := wb.author();
  run       uuid := wb.current_run();
  src       uuid := nullif(current_setting('wb.source', true), '')::uuid;
  evidence  jsonb := coalesce(nullif(current_setting('wb.evidence', true), '')::jsonb, '{}'::jsonb);
  newj      jsonb := to_jsonb(new);
  oldj      jsonb := case when tg_op = 'UPDATE' then to_jsonb(old) else '{}'::jsonb end;
  k         text;
  v         jsonb;
  cid       uuid;
begin
  for k, v in select key, value from jsonb_each(newj)
              where key not in ('id', 'created_at', 'updated_at', 'created_by', 'updated_by') loop
    continue when tg_op = 'INSERT' and v = 'null'::jsonb;
    continue when tg_op = 'UPDATE' and v is not distinct from oldj -> k;
    cid := null;
    insert into wb.claim (subject_type, subject_id, field, value, author, run_id, source_id, quote, span, hash)
    values (tg_table_name, new.id, k, v, who, run, src, evidence -> k ->> 'quote', evidence -> k -> 'span',
            md5(concat_ws('|', tg_table_name, new.id, k, v::text, who, coalesce(src::text, run::text))))
    on conflict (hash) where status = 'current' do nothing
    returning id into cid;
    if cid is not null then
      update wb.claim set status = 'superseded', superseded_by = cid
      where subject_type = tg_table_name and subject_id = new.id and field = k and status = 'current'
        and id <> cid and author is not distinct from who and object_id is null;
    end if;
  end loop;
  return null;
end $$;

-- ------------------------------------------------------------------ 2. a retracted premise takes its conclusions
create or replace function wb.retract_dependents() returns trigger
language plpgsql security definer set search_path = pg_catalog, wb as $$
begin
  if old.status = 'current' and new.status = 'retracted' then
    update wb.claim set status = 'retracted'
     where status = 'current' and jsonb_typeof(span -> 'premises') = 'array' and span -> 'premises' ? old.id::text;
    if old.object_id is not null then
      delete from wb.relation
       where from_type = old.subject_type and from_id = old.subject_id and predicate = old.field
         and to_type = old.object_type and to_id = old.object_id and author is not distinct from old.author;
    end if;
  end if;
  return null;
end $$;
create trigger wb_retract_dependents after update of status on wb.claim
  for each row when (old.status = 'current' and new.status = 'retracted') execute function wb.retract_dependents();
create index claim_premises on wb.claim using gin ((span -> 'premises')) where status = 'current';
create index claim_object on wb.claim (object_type, object_id) where object_id is not null;

-- ------------------------------------------------------------------ 3. terms that say how they relate
alter table wb.term add column comment text;
alter table wb.term add column parents text[] not null default '{}';
alter table wb.term add column characteristics text[] not null default '{}';
alter table wb.term add column inverse_of text;
alter table wb.term add column domain text;
alter table wb.term add column range text;
alter table wb.term add column plugin text;
alter table wb.term add column predicate text;          -- for a property: the relation predicate it names (wb.relation.predicate)
alter table wb.term drop constraint term_kind_check;
alter table wb.term add constraint term_kind_check
  check (kind in ('class', 'property', 'datatype-property', 'value', 'prefix'));
alter table wb.term add constraint term_characteristics_check
  check (characteristics <@ array['transitive', 'symmetric', 'functional', 'inverse-functional', 'reflexive']::text[]);

create or replace view api.terms with (security_invoker = true) as
  select iri, label, kind, vocabulary, comment, parents, characteristics, inverse_of, domain, range, plugin, predicate from wb.term;
grant select on wb.term, wb.mapping, api.terms to wb_viewer;

-- ------------------------------------------------------------------ 4. traversal
create extension if not exists graph;

-- A path between two items, following relations in their direction, as the caller (pgGraph applies the caller's
-- rights). Items by type and slug; relation steps show their predicate and who stated it.
create or replace function api.graph_path(from_type text, from_slug text, to_type text, to_slug text, max_depth integer default 12)
returns table (step integer, type text, slug text, title text, predicate text, author text)
language plpgsql stable security invoker set search_path = pg_catalog, graph as $$
declare
  a uuid;
  b uuid;
begin
  execute format('select id from content.%I where slug = $1', from_type) into a using from_slug;
  execute format('select id from content.%I where slug = $1', to_type) into b using to_slug;
  if a is null or b is null then
    return;
  end if;
  return query
    select p.step, case when p.node_table_name = 'relation' then 'relation' else p.node_table_name end,
           p.node ->> 'slug', p.node ->> 'title', p.node ->> 'predicate', p.node ->> 'author'
      from graph.path(format('content.%I', from_type)::regclass, a::text, format('content.%I', to_type)::regclass, b::text, max_depth) p
     order by p.step;
end $$;
grant execute on function api.graph_path(text, text, text, text, integer) to wb_viewer;
