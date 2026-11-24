-- The desktop as an environment (S-206; the product cut's step 2): a conversation between a person and the agents, kept
-- as signals, and gate policies a deployment sets for MCP tools before they first register.
--
--   desktop.<to>.<kind>  a signal: `to` is a person's role (person_owner) or `all`; kind is message (what a person
--                        says), reply (what an agent says), show (an agent puts something in front of the person: a
--                        view, an app or a claim), ask (an agent asks; the person answers with a message)
--   env.desktop_feed     a person's conversation after an id: what was said to them or to all, and what they said
--   env.mcp_policy       a gate for a server's tool, set before it registers: env.mcp_register gives a new tool this gate
--                        instead of the one its annotations suggest (a distribution's configuration, S-203)
--
-- Login: the desktop's server (role env_desktop) publishes desktop signals and reads the feed; nothing else.

create table env.mcp_policy (
  server  text not null check (server ~ '^[a-z][a-z0-9_]{0,30}$'),
  tool    text not null,
  gate    text not null check (gate in ('free', 'propose', 'deny')),
  set_by  text not null check (set_by <> ''),
  at      timestamptz not null default now(),
  primary key (server, tool)
);

-- 010's registration, now asking the policy first for a tool's first gate.
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
    end if;
    select a.queue into q from env.actuator a where a.name = act;
    perform env.allow(q, session_user);
    tool := env.mcp_exposed(p_server, t->>'name'); actuator := act; queue := q;
    gate := (select a.gate from env.actuator a where a.name = act);
    return next;
  end loop;
end $$;

-- The desktop's own tools change nothing but the conversation: a deployment lets them through (S-206).
insert into env.mcp_policy (server, tool, gate, set_by) values
  ('desktop', 'say', 'free', 'substrate'), ('desktop', 'show', 'free', 'substrate'),
  ('desktop', 'ask', 'free', 'substrate'), ('desktop', 'feed', 'free', 'substrate')
on conflict do nothing;

create function env.desktop_feed(p_person text, p_after bigint default 0, p_limit int default 100)
returns table (id bigint, to_ text, kind text, body jsonb, source text, at timestamptz)
language sql stable security definer set search_path = pg_catalog, public as $$
  select s.id, split_part(s.key, '.', 2), split_part(s.key, '.', 3), s.body, s.source, s.at
  from env.signal s
  where s.key like 'desktop.%' and s.id > coalesce(p_after, 0)
    and (split_part(s.key, '.', 2) in (p_person, 'all') or (s.source = p_person and split_part(s.key, '.', 3) = 'message'))
  order by s.id limit least(greatest(p_limit, 1), 500)
$$;

do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'env_desktop') then create role env_desktop nologin; end if;
end $$;
revoke all on function env.desktop_feed(text, bigint, int) from public;
grant usage on schema env to env_desktop;
grant execute on function env.publish(text, jsonb, text, jsonb), env.desktop_feed(text, bigint, int) to env_desktop;
