-- A tool's gate follows its annotations until a person sets it (S-218). 010 and 011 gave a tool its gate once, at its
-- first registration, and never changed it: tools registered before their server marked them read-only (the kernel's
-- D-128) stayed `propose`, so every read waited for a person. Now, on each registration, a gate whose `set_by` is the
-- registering connector (no person has set it since) is set again from the policy (env.mcp_policy), else from the
-- annotations: readOnlyHint true is `free`, anything else `propose`, in both directions. A gate a person set is kept.

create or replace function env.mcp_register(p_server text, p_transport text, p_target jsonb, p_info jsonb, p_tools jsonb, p_by text)
returns table (tool text, actuator text, queue text, gate text)
language plpgsql security definer set search_path = pg_catalog, public as $$
declare t jsonb; tid bigint; act text; q text; g text;
begin
  insert into env.mcp_server (name, transport, target, info, registered_by)
  values (p_server, p_transport, coalesce(p_target, '{}'), coalesce(p_info, '{}'), p_by)
  on conflict (name) do update set transport = excluded.transport, target = excluded.target, info = excluded.info,
    registered_by = excluded.registered_by, login = session_user, seen_at = now();
  update env.mcp_tool set present = false, updated_at = now()
  where server = p_server and present and name not in (select x->>'name' from jsonb_array_elements(p_tools) x);
  for t in select * from jsonb_array_elements(p_tools) loop
    select id, env.mcp_tool.actuator into tid, act from env.mcp_tool where server = p_server and name = t->>'name';
    if tid is null then
      tid := nextval(pg_get_serial_sequence('env.mcp_tool', 'id'));
      act := 'mcp.tool_' || tid;
      select p.gate into g from env.mcp_policy p where p.server = p_server and p.tool = t->>'name';
      g := coalesce(g, case when (t->'annotations'->>'readOnlyHint')::boolean then 'free' else 'propose' end);
      perform env.actuator(act, g, p_by, 'MCP tool ' || env.mcp_exposed(p_server, t->>'name'));
      insert into env.mcp_tool (id, server, name, title, description, input_schema, output_schema, annotations, actuator)
      values (tid, p_server, t->>'name', t->>'title', t->>'description', coalesce(t->'inputSchema', '{"type": "object"}'),
              t->'outputSchema', coalesce(t->'annotations', '{}'), act);
    else
      update env.mcp_tool set title = t->>'title', description = t->>'description',
        input_schema = coalesce(t->'inputSchema', '{"type": "object"}'), output_schema = t->'outputSchema',
        annotations = coalesce(t->'annotations', '{}'), present = true, updated_at = now()
      where id = tid;
      -- A gate no person has set (the connector that registers set it) follows the policy, then the annotations.
      select p.gate into g from env.mcp_policy p where p.server = p_server and p.tool = t->>'name';
      g := coalesce(g, case when (t->'annotations'->>'readOnlyHint')::boolean then 'free' else 'propose' end);
      if exists (select 1 from env.actuator a where a.name = act and a.set_by = p_by and a.gate <> g) then
        perform env.actuator(act, g, p_by);
      end if;
    end if;
    select a.queue into q from env.actuator a where a.name = act;
    perform env.allow(q, session_user);
    tool := env.mcp_exposed(p_server, t->>'name'); actuator := act; queue := q;
    gate := (select a.gate from env.actuator a where a.name = act);
    return next;
  end loop;
end $$;
