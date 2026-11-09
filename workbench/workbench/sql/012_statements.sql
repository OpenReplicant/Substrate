-- Statements: a claim that a source makes about an item, recorded beside the item's value rather than written over
-- it. A transcript quoting a person is the case in mind: the person is the claim's author, the extractor run that
-- read the transcript is its run, and the quote is the person's words. If the statement disagrees with the item's
-- current value, the item keeps its value and the extractor raises the disagreement for review.
--
-- wb.state_claim records one (returning its id, or the id of the same current claim if it was already stated), and
-- supersedes that author's earlier claim on the same field of the same item. wb.retract_unstated retracts what an
-- extractor's runs stated before and no longer state (the statement was taken out of its source).

create function wb.state_claim(p_type text, p_id uuid, p_field text, p_value jsonb, p_author text, p_source uuid,
                               p_quote text, p_span jsonb) returns uuid
language plpgsql security definer set search_path = pg_catalog, wb as $$
declare
  run uuid := wb.current_run();
  h   text := md5(concat_ws('|', p_type, p_id, p_field, p_value::text, p_author, coalesce(p_source::text, ''), 'stated'));
  cid uuid;
begin
  if p_author is null or p_author = '' then
    raise exception 'a statement needs the name of who made it';
  end if;
  select id into cid from wb.claim where hash = h and status = 'current';
  if cid is not null then
    return cid;
  end if;
  insert into wb.claim (subject_type, subject_id, field, value, author, run_id, source_id, quote, span, hash)
  values (p_type, p_id, p_field, p_value, p_author, run, p_source, p_quote, p_span, h)
  returning id into cid;
  update wb.claim set status = 'superseded', superseded_by = cid
   where subject_type = p_type and subject_id = p_id and field = p_field and status = 'current'
     and author is not distinct from p_author and object_id is null and id <> cid;
  return cid;
end $$;

create function wb.retract_unstated(p_extractor text, p_keep uuid[]) returns integer
language plpgsql security definer set search_path = pg_catalog, wb as $$
declare n integer;
begin
  update wb.claim c set status = 'retracted'
   where c.status = 'current' and c.object_id is null and c.author is distinct from p_extractor
     and c.run_id in (select r.id from wb.run r where r.extractor = p_extractor)
     and not (c.id = any(p_keep));
  get diagnostics n = row_count;
  return n;
end $$;

revoke execute on function wb.state_claim(text, uuid, text, jsonb, text, uuid, text, jsonb),
                           wb.retract_unstated(text, uuid[]) from public;
grant execute on function wb.state_claim(text, uuid, text, jsonb, text, uuid, text, jsonb),
                          wb.retract_unstated(text, uuid[]) to wb_server;
