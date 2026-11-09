-- W3: the server's queue, live events, extractor evidence, and what a source no longer says (BRIEF.md 3, 7).
-- wb_server is created by `workbench migrate` (it needs a password); this file gives it what it may do.

-- ------------------------------------------------------------------ jobs: durable work on pgmq
create extension if not exists pgmq;
select pgmq.create('wb_jobs');

-- ------------------------------------------------------------------ live events: NOTIFY, relayed by the server
-- A payload names what changed, never its content: subscribers fetch it through the API under their own token.
create function wb.notify_item() returns trigger language plpgsql as $$
begin
  perform pg_notify('wb_events', json_build_object('kind', 'item', 'type', tg_table_name, 'id', new.id,
                                                   'op', lower(tg_op), 'author', wb.author())::text);
  return null;
end $$;

create function wb.notify_decision() returns trigger language plpgsql as $$
begin
  perform pg_notify('wb_events', json_build_object('kind', 'decision', 'id', new.id, 'status', new.status)::text);
  return null;
end $$;
create trigger wb_events after insert or update on wb.decision for each row execute function wb.notify_decision();

create function wb.notify_run() returns trigger language plpgsql as $$
begin
  perform pg_notify('wb_events', json_build_object('kind', 'run', 'id', new.id, 'extractor', new.extractor,
                                                   'done', new.ended_at is not null)::text);
  return null;
end $$;
create trigger wb_events after insert or update on wb.run for each row execute function wb.notify_run();

-- ------------------------------------------------------------------ claims from extractors carry their evidence
-- An extractor's write sets, for its transaction: wb.author (its name), wb.run, wb.source (the source row) and
-- wb.evidence ({field: {quote, span}}). The same value from the same source is the same claim, whichever run
-- read it, so re-reading an unchanged file adds nothing.
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
        and id <> cid and author is not distinct from who;
    end if;
  end loop;
  return null;
end $$;

-- When a source no longer states something: an extractor that read a whole source names the items it found; the
-- current claims it made earlier about other items of that type are retracted (the items stay; nothing is deleted).
create function wb.retract_missing(p_author text, p_type text, p_keep uuid[]) returns integer
language plpgsql security definer set search_path = pg_catalog, wb as $$
declare n integer;
begin
  update wb.claim set status = 'retracted'
   where author = p_author and subject_type = p_type and status = 'current' and not (subject_id = any(p_keep));
  get diagnostics n = row_count;
  return n;
end $$;
revoke execute on function wb.retract_missing(text, text, uuid[]) from public;

-- ------------------------------------------------------------------ decisions an extractor raises, and withdraws
alter table wb.decision drop constraint decision_status_check;
alter table wb.decision add constraint decision_status_check check (status in ('open', 'approved', 'declined', 'withdrawn'));
alter table wb.decision add column key text;          -- the raiser's own name for it, so raising again is a no-op
alter table wb.decision add column raised_by text;
create unique index decision_open_key on wb.decision (raised_by, key) where status = 'open';

-- ------------------------------------------------------------------ what the shell shows about runs and sources
create view api.runs with (security_invoker = true) as
  select id, extractor, plugin, version, inputs, started_at, ended_at, outcome from wb.run;
create view api.sources with (security_invoker = true) as
  select id, uri, sha256, media_type, retrieved_at from wb.source;
create or replace view api.decisions with (security_invoker = true) as
  select id, kind, subject, evidence, status, decided_by, decided_at, note, created_at, key, raised_by from wb.decision;
create view api.relations with (security_invoker = true) as
  select id, from_type, from_id, predicate, to_type, to_id, created_at from wb.relation;
grant select on wb.run, wb.source, wb.relation, api.runs, api.sources, api.relations to wb_viewer;
grant select on api.decisions to wb_viewer;

-- ------------------------------------------------------------------ the server's own rights
grant usage on schema pgmq to wb_server;
grant select, insert, update, delete on pgmq.q_wb_jobs, pgmq.a_wb_jobs to wb_server;
grant execute on all functions in schema pgmq to wb_server;
grant usage, select on all sequences in schema pgmq to wb_server;
grant insert, update on wb.run to wb_server;
grant insert, update on wb.source to wb_server;
grant insert, delete on wb.relation to wb_server;
grant insert, update (status, decided_by, decided_at, note, evidence, subject) on wb.decision to wb_server;
grant execute on function wb.retract_missing(text, text, uuid[]) to wb_server;
-- editors and owners may queue work from the shell (the server checks the token's role before it does)
