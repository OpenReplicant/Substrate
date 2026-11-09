-- Retiring an item (BRIEF.md section 2: nobody deletes). Every current claim behind it is retracted, so it no
-- longer stands as stated, and the retirement is itself a claim: field `_retired`, the note as its value, by the
-- caller, naming the claims it retracted in its span. What rested on those claims goes with them
-- (wb_retract_dependents). `api.restore` undoes it: the same claims become current again, except where something
-- newer was written; a relation's row and what rested on the claims come back only when whoever stated them
-- states them again (an extractor's next run). `wb.live` says whether an item stands: some value of it currently
-- stated (a relation from it does not count, nor a retirement).

create function wb.live(p_id uuid) returns boolean language sql stable as $$
  select exists (select 1 from wb.claim
                  where subject_id = p_id and status in ('current', 'disputed') and field <> '_retired' and object_id is null)
$$;

create function api.retire(type text, id uuid, note text default null) returns json
language plpgsql security definer set search_path = pg_catalog, wb as $$
declare
  t    text := retire.type;
  ids  uuid[];
  who  text := wb.author();
begin
  if not exists (select 1 from wb.content_type c where c.id = t) then
    raise exception 'no content type %', t using errcode = 'no_data_found';
  end if;
  with r as (
    update wb.claim set status = 'retracted'
     where subject_type = t and subject_id = retire.id and status in ('current', 'disputed') and field <> '_retired'
    returning wb.claim.id)
  select array_agg(r.id) into ids from r;
  if ids is null then
    raise exception 'nothing stands behind % % to retire', t, retire.id using errcode = 'no_data_found';
  end if;
  insert into wb.claim (subject_type, subject_id, field, value, author, run_id, quote, span, hash)
  values (t, retire.id, '_retired', to_jsonb(coalesce(note, '')), who, wb.current_run(), note,
          jsonb_build_object('retracted', to_jsonb(ids)),
          md5(concat_ws('|', t, retire.id, '_retired', clock_timestamp()::text, who)));
  perform pg_notify('wb_events', json_build_object('kind', 'item', 'type', t, 'id', retire.id, 'op', 'retire', 'author', who)::text);
  return json_build_object('type', t, 'id', retire.id, 'retracted', cardinality(ids), 'by', who);
end $$;

create function api.restore(type text, id uuid) returns json
language plpgsql security definer set search_path = pg_catalog, wb as $$
declare
  t    text := restore.type;
  mark wb.claim;
  cnt  integer;
begin
  select * into mark from wb.claim
   where subject_type = t and subject_id = restore.id and field = '_retired' and status = 'current'
   order by observed_at desc limit 1;
  if mark.id is null then
    raise exception '% % is not retired', t, restore.id using errcode = 'no_data_found';
  end if;
  -- only claims nothing newer has replaced: a field written since stays as written
  update wb.claim c set status = 'current'
   where c.id in (select (jsonb_array_elements_text(mark.span -> 'retracted'))::uuid) and c.status = 'retracted'
     and not exists (select 1 from wb.claim w where w.subject_id = c.subject_id and w.field = c.field
                       and w.status = 'current' and w.author is not distinct from c.author);
  get diagnostics cnt = row_count;
  update wb.claim set status = 'superseded' where wb.claim.id = mark.id;
  perform pg_notify('wb_events', json_build_object('kind', 'item', 'type', t, 'id', restore.id, 'op', 'restore', 'author', wb.author())::text);
  return json_build_object('type', t, 'id', restore.id, 'restored', cnt, 'by', wb.author());
end $$;

revoke execute on function api.retire(text, uuid, text), api.restore(text, uuid) from public;
grant execute on function api.retire(text, uuid, text), api.restore(text, uuid) to wb_editor;
grant execute on function wb.live(uuid) to wb_viewer;
