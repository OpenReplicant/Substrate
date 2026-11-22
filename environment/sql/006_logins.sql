-- Logins in the environment (plan step 4): a process that runs a model (the companion's container) connects as a
-- login of its own, which may publish, act, escalate and read the queues it is given, and may not decide a
-- proposal, change a gate or read the record. Who connected is kept on every signal and action, where a process
-- cannot claim to be someone else (its `source` and `caller` are what it says; `login` is what Postgres saw).
--
--   env.allow(queue, login)        a login may read and acknowledge that queue (the owner's call)
--   env.read(queue, vt, qty)       pgmq.read through that check; env.ack(queue, ids) pgmq.archive through it
--   env.setting                    an environment's settings (a model, a budget), each change a row: set by an
--                                  applied action or a person, never edited; env.set(...) adds one
--
-- The functions run as their owner (security definer) and execute is granted by name, so what a login can do is
-- this list and nothing else.

alter table env.signal add column login text not null default session_user;
alter table env.action add column login text not null default session_user;

create or replace function env.signal_guard() returns trigger language plpgsql as $$
begin
  if tg_op = 'UPDATE' and (new.id, new.key, new.body, new.headers, new.source, new.at, new.login)
                          is not distinct from (old.id, old.key, old.body, old.headers, old.source, old.at, old.login) then
    return new;                                                         -- only reached is set, once, by publish
  end if;
  raise exception 'env: a signal is kept whole: it is not changed or deleted';
end $$;

create table env.reader (
  queue  text not null,
  login  text not null,
  primary key (queue, login)
);

create function env.allow(p_queue text, p_login text) returns void language sql as $$
  insert into env.reader values (env.check_name(p_queue), p_login) on conflict do nothing
$$;

create function env.may_read(p_queue text) returns boolean language sql stable as $$
  select exists (select 1 from pg_roles where rolname = session_user and rolsuper)
      or exists (select 1 from env.reader where queue = p_queue and login = session_user)
$$;

create function env.read(p_queue text, p_vt int, p_qty int)
returns table (msg_id bigint, read_ct int, message jsonb) language plpgsql security definer set search_path = pg_catalog, pgmq as $$
begin
  if not env.may_read(p_queue) then raise exception 'env: % may not read queue %', session_user, p_queue; end if;
  return query select r.msg_id, r.read_ct, r.message from pgmq.read(p_queue, p_vt, p_qty) r;
end $$;

create function env.ack(p_queue text, p_ids bigint[]) returns setof bigint
language plpgsql security definer set search_path = pg_catalog, pgmq as $$
begin
  if not env.may_read(p_queue) then raise exception 'env: % may not acknowledge on queue %', session_user, p_queue; end if;
  return query select pgmq.archive(p_queue, p_ids);
end $$;

-- A subscriber made by a login is readable by it; binding patterns to someone else's queue is refused.
create or replace function env.subscribe(p_queue text, p_patterns text[]) returns void language plpgsql as $$
declare pat text;
begin
  perform env.check_name(p_queue);
  if not exists (select 1 from pgmq.meta where queue_name = p_queue) then
    perform pgmq.create(p_queue);
    perform env.allow(p_queue, session_user);
  elsif not env.may_read(p_queue) then
    raise exception 'env: queue % is not %''s', p_queue, session_user;
  end if;
  foreach pat in array p_patterns loop
    perform pgmq.bind_topic(pat, p_queue);
  end loop;
end $$;

-- The process applying an actuator reports on its own actions only: a login may report done on an actuator's
-- action when it may read that actuator's queue.
create or replace function env.done(p_action bigint, p_result jsonb, p_ok boolean default true) returns void language plpgsql as $$
declare a env.action; q text;
begin
  select queue into q from env.actuator where name = (select actuator from env.action where id = p_action);
  if q is not null and not env.may_read(q) then
    raise exception 'env: % does not apply action %', session_user, p_action;
  end if;
  update env.action set status = case when p_ok then 'applied' else 'failed' end, result = p_result, done_at = now()
  where id = p_action and status = 'queued' returning * into a;
  if a.id is null then raise exception 'env: action % is not queued', p_action; end if;
  perform pgmq.archive(q, a.msg_id);
end $$;

create table env.setting (
  id      bigserial primary key,
  env     text not null check (env ~ '^[a-z0-9_]+$'),
  name    text not null check (name ~ '^[a-z0-9_]+$'),
  value   jsonb not null,
  set_by  text not null check (set_by <> ''),
  action  bigint references env.action,         -- the applied action that set it, when one did
  login   text not null default session_user,
  at      timestamptz not null default now()
);
create index setting_current on env.setting (env, name, id desc);

create function env.set(p_env text, p_name text, p_value jsonb, p_by text, p_action bigint default null) returns bigint
language sql as $$
  insert into env.setting (env, name, value, set_by, action) values (p_env, p_name, p_value, p_by, p_action) returning id
$$;

create view env.current as
  select distinct on (env, name) env, name, value, set_by, action, at from env.setting order by env, name, id desc;

create function env.get(p_env text, p_name text) returns jsonb language sql stable security definer as $$
  select value from env.current where env = p_env and name = p_name
$$;

-- What a model's login may do: these, and nothing else in env or pgmq.
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'env_agent') then
    create role env_agent nologin;
  end if;
end $$;
revoke all on all functions in schema env from public;
alter function env.publish(text, jsonb, text, jsonb) security definer set search_path = pg_catalog, public;
alter function env.escalate(text, jsonb, text) security definer set search_path = pg_catalog, public;
alter function env.act(text, jsonb, text) security definer set search_path = pg_catalog, public;
alter function env.subscribe(text, text[]) security definer set search_path = pg_catalog, public;
alter function env.done(bigint, jsonb, boolean) security definer set search_path = pg_catalog, public;
alter function env.get(text, text) set search_path = pg_catalog, public;
grant usage on schema env to env_agent;
grant execute on function env.publish(text, jsonb, text, jsonb), env.escalate(text, jsonb, text),
  env.act(text, jsonb, text), env.subscribe(text, text[]), env.done(bigint, jsonb, boolean),
  env.read(text, int, int), env.ack(text, bigint[]), env.get(text, text), env.check_name(text) to env_agent;
