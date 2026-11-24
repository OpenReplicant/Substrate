-- MCP servers and their tools as objects in the environment (S-205; S-203: modules meet over MCP; the router's rules
-- live here, in the database, and its network edge and connectors are processes outside it).
--
--   mcp_server  a server a connector reaches (stdio, HTTP, anything): its name, how it is reached, what it said it is
--   mcp_tool    each tool it lists: name, schema, annotations; each tool is an actuator (mcp.tool_<id>), so a call is an
--               env.action behind that actuator's gate, on its queue, recorded whole like every other action
--   a call      the router's env.mcp_call -> env.act: free is queued at once, propose waits for a person (decided in the
--               desktop), deny is refused; the server's connector reads the queue, calls the tool, reports env.done;
--               every change of an action's status is announced on the channel `env_action`, so the router answers the
--               caller as soon as it is decided or done
--
-- A tool's gate starts from its annotations: readOnlyHint true is `free`, anything else `propose` (MCP's own default
-- for a tool without hints is "may change the world"). A person changes it like any actuator's (env.actuator); a
-- connector registering again never changes a gate. A tool a server stops listing is kept, marked absent.
--
-- Logins: the router (role env_router) lists tools, calls them for a caller it has authenticated, reads an action's
-- outcome and records a person's decision; a connector (role env_connector) registers its server and applies the
-- actions on its tools' queues. Nothing else.

create table env.mcp_server (
  name           text primary key check (name ~ '^[a-z][a-z0-9_]{0,30}$'),
  transport      text not null check (transport in ('stdio', 'http', 'other')),
  target         jsonb not null default '{}',          -- how it is reached: {command, args} or {url}; never a secret
  info           jsonb not null default '{}',          -- what it said: serverInfo, protocolVersion, instructions
  registered_by  text not null check (registered_by <> ''),
  login          text not null default session_user,
  seen_at        timestamptz not null default now()    -- its connector's last registration
);

create table env.mcp_tool (
  id             bigserial primary key,
  server         text not null references env.mcp_server on delete restrict,
  name           text not null,                        -- the tool's own name on its server
  title          text,
  description    text,
  input_schema   jsonb not null default '{"type": "object"}',
  output_schema  jsonb,
  annotations    jsonb not null default '{}',
  actuator       text not null unique,                 -- mcp.tool_<id>
  present        boolean not null default true,        -- false once its server stops listing it
  updated_at     timestamptz not null default now(),
  unique (server, name)
);

-- The name a client sees: <server>_<tool>, as other routers prefix them.
create function env.mcp_exposed(p_server text, p_name text) returns text language sql immutable as $$
  select p_server || '_' || p_name
$$;

-- A connector registers its server and the tools it lists; returns each tool's actuator, queue and gate. New tools get
-- an actuator with the gate their annotations suggest; existing ones keep theirs; ones no longer listed are marked absent.
create function env.mcp_register(p_server text, p_transport text, p_target jsonb, p_info jsonb, p_tools jsonb, p_by text)
returns table (tool text, actuator text, queue text, gate text)
language plpgsql security definer set search_path = pg_catalog, public as $$
declare t jsonb; tid bigint; act text; q text;
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
      perform env.actuator(act, case when (t->'annotations'->>'readOnlyHint')::boolean then 'free' else 'propose' end,
                           p_by, 'MCP tool ' || env.mcp_exposed(p_server, t->>'name'));
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
    perform env.allow(q, session_user);                  -- the connector that registered it applies its calls
    tool := env.mcp_exposed(p_server, t->>'name'); actuator := act; queue := q;
    gate := (select a.gate from env.actuator a where a.name = act);
    return next;
  end loop;
end $$;

-- What the router lists: every present tool whose gate is not deny, by its exposed name.
create function env.mcp_tools()
returns table (name text, server text, tool text, title text, description text, input_schema jsonb, output_schema jsonb,
               annotations jsonb, gate text, actuator text)
language sql stable security definer set search_path = pg_catalog, public as $$
  select env.mcp_exposed(t.server, t.name), t.server, t.name, t.title, t.description, t.input_schema, t.output_schema,
         t.annotations, a.gate, t.actuator
  from env.mcp_tool t join env.actuator a on a.name = t.actuator
  where t.present and a.gate <> 'deny'
  order by 1
$$;

-- The router calls a tool for a caller it has authenticated (p_by: the caller's role, from its token).
create function env.mcp_call(p_tool text, p_arguments jsonb, p_by text, out action bigint, out status text)
language plpgsql security definer set search_path = pg_catalog, public as $$
declare t env.mcp_tool;
begin
  select * into t from env.mcp_tool where env.mcp_exposed(server, name) = p_tool and present;
  if t.id is null then raise exception 'env: no MCP tool %', p_tool; end if;
  select a.action, a.status into action, status
  from env.act(t.actuator, jsonb_build_object('server', t.server, 'tool', t.name, 'arguments', coalesce(p_arguments, '{}')),
               p_by) a;
end $$;

-- An action's outcome, for the router to answer with (and for a caller asking about one that waited).
create function env.mcp_outcome(p_action bigint)
returns table (id bigint, tool text, caller text, status text, result jsonb, reason text, decided_by text, at timestamptz,
               done_at timestamptz)
language sql stable security definer set search_path = pg_catalog, public as $$
  select a.id, env.mcp_exposed(a.input->>'server', a.input->>'tool'), a.caller, a.status, a.result, a.reason,
         a.decided_by, a.at, a.done_at
  from env.action a where a.id = p_action and a.actuator like 'mcp.%'
$$;

-- The record, for the router's page: the latest calls through it, newest first.
create function env.mcp_calls(p_limit int default 100)
returns table (id bigint, tool text, caller text, gate text, status text, arguments jsonb, result jsonb, reason text,
               decided_by text, at timestamptz, done_at timestamptz)
language sql stable security definer set search_path = pg_catalog, public as $$
  select a.id, env.mcp_exposed(a.input->>'server', a.input->>'tool'), a.caller, a.gate, a.status, a.input->'arguments',
         a.result, a.reason, a.decided_by, a.at, a.done_at
  from env.action a where a.actuator like 'mcp.%' order by a.id desc limit least(greatest(p_limit, 1), 1000)
$$;

-- Every status an action takes is announced, so the router waits on a notification, not a poll.
create function env.action_notify() returns trigger language plpgsql as $$
begin
  perform pg_notify('env_action', json_build_object('id', new.id, 'status', new.status)::text);
  return new;
end $$;
create trigger action_announced after insert or update of status on env.action
  for each row execute function env.action_notify();

-- The roles. Logins are made by scripts/db.py with passwords from .env and granted one of these.
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'env_router') then create role env_router nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'env_connector') then create role env_connector nologin; end if;
end $$;
revoke all on function env.mcp_register(text, text, jsonb, jsonb, jsonb, text), env.mcp_tools(), env.mcp_call(text, jsonb, text),
  env.mcp_outcome(bigint), env.mcp_calls(int) from public;
alter function env.decide(bigint, boolean, text, text) security definer set search_path = pg_catalog, public;
grant usage on schema env to env_router, env_connector;
grant execute on function env.mcp_tools(), env.mcp_call(text, jsonb, text), env.mcp_outcome(bigint), env.mcp_calls(int),
  env.decide(bigint, boolean, text, text), env.mcp_exposed(text, text) to env_router;
grant execute on function env.mcp_register(text, text, jsonb, jsonb, jsonb, text), env.read(text, int, int),
  env.ack(text, bigint[]), env.done(bigint, jsonb, boolean), env.check_name(text), env.mcp_exposed(text, text) to env_connector;
