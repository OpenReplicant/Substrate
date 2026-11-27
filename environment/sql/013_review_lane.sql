-- The environment as a kernel module (S-219): a proposal waits in the kernel's review lane, so a person approves in one
-- place, the desktop's Review. The module's process (environment/review.py, role kkm_environment) submits each waiting
-- action as a change set in the review lane and, once a person has approved or rejected it there, records that person's
-- decision here with env.decide. The kernel's side of the install (the role's agent row, its clearance) is
-- environment/migration.sql, which `kk module install` applies; this file is the environment's side, safe in either order.
--
--   env.review_waiting()  the actions waiting for a person, with what the review lane shows of each
--   env.decide            now called only by the module (and a superuser): the router no longer decides (S-219)
--
-- The channel (environment/channel.py) gets a login of its own (S-220): mcp_channel, role env_agent, so a harness's
-- channel acts through the gates and reads only the queues it subscribed, never as a superuser.

do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'kkm_environment') then
    create role kkm_environment nologin;
  end if;
end $$;

create function env.review_waiting(p_limit int default 200)
returns table (id bigint, actuator text, description text, input jsonb, caller text, login text, at timestamptz)
language sql stable security definer set search_path = pg_catalog, public as $$
  select a.id, a.actuator, u.description, a.input, a.caller, a.login, a.at
  from env.action a join env.actuator u on u.name = a.actuator
  where a.status = 'proposed'
  order by a.id limit least(greatest(p_limit, 1), 1000)
$$;

revoke all on function env.review_waiting(int) from public;
revoke execute on function env.decide(bigint, boolean, text, text) from env_router;
grant usage on schema env to kkm_environment;
grant execute on function env.review_waiting(int), env.decide(bigint, boolean, text, text) to kkm_environment;

-- Queues the assistant's channel made while it connected as a superuser (S-206) become the channel login's, so it can
-- subscribe to them again under its own login.
insert into env.reader (queue, login)
select queue_name, 'mcp_channel' from pgmq.meta where queue_name like 'assistant\_%'
on conflict do nothing;
