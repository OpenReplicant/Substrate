-- The review lane over the API (BRIEF.md section 4): viewers see decisions, editors and owners make them.
-- `decide` runs as the caller, so the grants below are what allow it; who decided comes from the JWT.

create view api.decisions with (security_invoker = true) as
  select id, kind, subject, evidence, status, decided_by, decided_at, note, created_at from wb.decision;

create function api.decide(id uuid, approve boolean, note text default null) returns json
language plpgsql as $$
declare
  d wb.decision;
begin
  update wb.decision
     set status = case when approve then 'approved' else 'declined' end,
         decided_by = wb.author(), decided_at = now(), note = decide.note
   where wb.decision.id = decide.id and status = 'open'
  returning * into d;
  if d.id is null then
    raise exception 'no open decision %', decide.id using errcode = 'no_data_found';
  end if;
  return json_build_object('id', d.id, 'status', d.status, 'decided_by', d.decided_by, 'decided_at', d.decided_at);
end $$;

revoke execute on function api.decide(uuid, boolean, text) from public;
grant select on wb.decision, api.decisions to wb_viewer;
grant update (status, decided_by, decided_at, note) on wb.decision to wb_editor;
grant execute on function api.decide(uuid, boolean, text) to wb_editor;
