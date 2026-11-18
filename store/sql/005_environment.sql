-- The real-time environment (plan step 3c, docs/framework.md "The environment is data"), on pgmq in the same
-- Postgres as the store.
--
--   signal     what a source reports, kept whole and in order: env.publish logs it here, then pgmq.send_topic
--              fans it out under its routing key <env>.<stream>.<kind> to every queue bound to a matching pattern
--   subscriber a pgmq queue of its own, bound to the patterns it watches (env.subscribe; * one segment, # any)
--   actuator   one pgmq queue per actuator (act_<name>), read by the one process that applies it, behind a gate:
--              free (queued at once), propose (waits for a person's decision), deny (refused)
--   action     every call on an actuator, whatever its gate said, and what became of it: the record of acting
--
-- Proposals are announced on <env>.review.proposed and their outcome on <env>.review.decided, so a subscriber
-- (the channel, the UI) sees both; escalation is the topic <env>.escalate, which the level above subscribes to.

create extension if not exists pgmq;
create schema env;

create table env.signal (
  id       bigserial primary key,
  key      text not null check (key ~ '^[a-z0-9_]+(\.[a-z0-9_]+)+$'),   -- <env>.<stream>[.<kind>...]
  body     jsonb not null,
  headers  jsonb not null default '{}',
  source   text not null check (source <> ''),                          -- who or what reported it
  at       timestamptz not null default now(),
  reached  int not null default 0                                       -- how many queues it was sent to
);
create index signal_key on env.signal (key, at);

create function env.signal_guard() returns trigger language plpgsql as $$
begin
  if tg_op = 'UPDATE' and (new.id, new.key, new.body, new.headers, new.source, new.at)
                          is not distinct from (old.id, old.key, old.body, old.headers, old.source, old.at) then
    return new;                                                         -- only reached is set, once, by publish
  end if;
  raise exception 'env: a signal is kept whole: it is not changed or deleted';
end $$;
create trigger signal_whole before update or delete on env.signal for each row execute function env.signal_guard();

create function env.check_name(p_name text) returns text language plpgsql immutable as $$
begin
  if p_name !~ '^[a-z][a-z0-9_]{0,39}$' then
    raise exception 'env: a queue name is a lowercase letter, then letters, digits or _ (at most 40): %', p_name;
  end if;
  return p_name;
end $$;

-- A subscriber's queue, made if missing, bound to each pattern (bindings are added, never dropped here).
create function env.subscribe(p_queue text, p_patterns text[]) returns void language plpgsql as $$
declare pat text;
begin
  perform env.check_name(p_queue);
  if not exists (select 1 from pgmq.meta where queue_name = p_queue) then
    perform pgmq.create(p_queue);
  end if;
  foreach pat in array p_patterns loop
    perform pgmq.bind_topic(pat, p_queue);
  end loop;
end $$;

-- Log a signal and fan it out; returns its id. Each queue gets {signal, key, by, at, body}.
create function env.publish(p_key text, p_body jsonb, p_by text, p_headers jsonb default '{}') returns bigint
language plpgsql as $$
declare sid bigint; n int; at_ timestamptz;
begin
  insert into env.signal (key, body, headers, source) values (p_key, p_body, coalesce(p_headers, '{}'), p_by)
  returning id, at into sid, at_;
  n := pgmq.send_topic(p_key, jsonb_build_object('signal', sid, 'key', p_key, 'by', p_by, 'at', at_, 'body', p_body),
                       coalesce(p_headers, '{}'), 0);
  update env.signal set reached = n where id = sid;
  return sid;
end $$;

create function env.escalate(p_env text, p_body jsonb, p_by text) returns bigint language sql as $$
  select env.publish(p_env || '.escalate', p_body, p_by)
$$;

create table env.actuator (
  name         text primary key check (name ~ '^[a-z0-9_]+\.[a-z0-9_]+$'),   -- <env>.<actuator>
  queue        text not null unique,
  gate         text not null check (gate in ('free', 'propose', 'deny')),
  description  text,
  set_by       text not null,
  set_at       timestamptz not null default now()
);

-- Make an actuator, or change its gate (who set it is kept; live work starts at propose).
create function env.actuator(p_name text, p_gate text, p_by text, p_description text default null) returns text
language plpgsql as $$
declare q text := env.check_name('act_' || replace(p_name, '.', '_'));
begin
  insert into env.actuator (name, queue, gate, description, set_by) values (p_name, q, p_gate, p_description, p_by)
  on conflict (name) do update set gate = excluded.gate, set_by = excluded.set_by, set_at = now(),
                                   description = coalesce(excluded.description, env.actuator.description);
  if not exists (select 1 from pgmq.meta where queue_name = q) then
    perform pgmq.create(q);
  end if;
  return q;
end $$;

create table env.action (
  id          bigserial primary key,
  actuator    text not null references env.actuator,
  input       jsonb not null,
  caller      text not null check (caller <> ''),
  at          timestamptz not null default now(),
  gate        text not null,                      -- the actuator's gate when it was called
  status      text not null check (status in ('queued', 'proposed', 'denied', 'refused', 'applied', 'failed')),
  msg_id      bigint,                             -- its message on the actuator's queue, once queued
  decided_by  text,                               -- the person who approved or refused a proposal
  decided_at  timestamptz,
  reason      text,
  result      jsonb,
  done_at     timestamptz
);
create index action_waiting on env.action (actuator) where status = 'proposed';

create function env.enqueue(a env.action) returns bigint language sql as $$
  select pgmq.send((select queue from env.actuator where name = a.actuator),
                   jsonb_build_object('action', a.id, 'actuator', a.actuator, 'input', a.input, 'by', a.caller))
$$;

-- Call an actuator through its gate. Returns the action's id and status (queued, proposed or denied).
create function env.act(p_actuator text, p_input jsonb, p_by text, out action bigint, out status text)
language plpgsql as $$
declare g text; a env.action;
begin
  select gate into g from env.actuator where name = p_actuator;
  if g is null then raise exception 'env: no actuator %', p_actuator; end if;
  insert into env.action (actuator, input, caller, gate, status)
  values (p_actuator, p_input, p_by, g, case g when 'free' then 'queued' when 'propose' then 'proposed' else 'denied' end)
  returning * into a;
  if g = 'free' then
    update env.action set msg_id = env.enqueue(a) where id = a.id;
  elsif g = 'propose' then
    perform env.publish(split_part(p_actuator, '.', 1) || '.review.proposed',
                        jsonb_build_object('action', a.id, 'actuator', p_actuator, 'input', p_input, 'by', p_by), 'env');
  end if;
  action := a.id; status := a.status;
end $$;

-- A person decides a proposal: approved, it is queued; refused, it never is. No one decides their own.
create function env.decide(p_action bigint, p_approve boolean, p_person text, p_reason text default null) returns text
language plpgsql as $$
declare a env.action;
begin
  select * into a from env.action where id = p_action for update;
  if a.id is null then raise exception 'env: no action %', p_action; end if;
  if a.status <> 'proposed' then raise exception 'env: action % is %, not waiting for a decision', p_action, a.status; end if;
  if coalesce(p_person, '') = '' or p_person = a.caller then
    raise exception 'env: a proposal is decided by a person other than the one who made it';
  end if;
  update env.action set status = case when p_approve then 'queued' else 'refused' end,
         decided_by = p_person, decided_at = now(), reason = p_reason
  where id = p_action returning * into a;
  if p_approve then
    update env.action set msg_id = env.enqueue(a) where id = a.id;
  end if;
  perform env.publish(split_part(a.actuator, '.', 1) || '.review.decided',
                      jsonb_build_object('action', a.id, 'actuator', a.actuator, 'approved', p_approve,
                                         'by', p_person, 'reason', p_reason), 'env');
  return a.status;
end $$;

-- The actuator's process reports an action applied (or failed); its message is archived.
create function env.done(p_action bigint, p_result jsonb, p_ok boolean default true) returns void language plpgsql as $$
declare a env.action;
begin
  update env.action set status = case when p_ok then 'applied' else 'failed' end, result = p_result, done_at = now()
  where id = p_action and status = 'queued' returning * into a;
  if a.id is null then raise exception 'env: action % is not queued', p_action; end if;
  perform pgmq.archive((select queue from env.actuator where name = a.actuator), a.msg_id);
end $$;
