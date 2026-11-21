-- Components and the judge (docs/framework.md, "Components and their cards" and "The judge is an interface"):
-- every version of a component is a row with its card; a judge outside its author's reach tests a candidate
-- against the incumbent on cases the author cannot read; a person activates what the judge found better.
--
--   component   a version of a component of an environment (env, name, version), its card, its status:
--               proposed -> judging -> judged (better than the incumbent) or refused -> active -> retired
--   verdict     a judge's result for a candidate against an incumbent: each KPI for both, case counts, outcome
--   held_out    which recorded signals are the judge's alone: a fixed share chosen by hash, never shown to an author
--
-- Who may do what (the functions run as their owner; execute is granted by name):
--   env_agent   (an author, e.g. the companion's container) submits a component; reads the training slice
--   env_judge   (the judge's login) claims a proposed one, reads everything, records its verdict
--   the owner   activates a judged component (through an approved proposal), retires one

create table env.component (
  id          bigserial primary key,
  env         text not null check (env ~ '^[a-z0-9_]+$'),
  name        text not null check (name ~ '^[a-z0-9_]+$'),
  version     int not null,
  card        jsonb not null check (jsonb_typeof(card) = 'object' and card ? 'intent' and card ? 'params'),
  status      text not null check (status in ('proposed', 'judging', 'judged', 'refused', 'active', 'retired')),
  against     bigint references env.component,           -- the incumbent it was proposed to replace
  author      text not null check (author <> ''),
  login       text not null default session_user,
  at          timestamptz not null default now(),
  status_at   timestamptz not null default now(),
  status_by   text,
  unique (env, name, version)
);
create unique index component_one_active on env.component (env, name) where status = 'active';

create table env.verdict (
  id          bigserial primary key,
  component   bigint not null references env.component,
  against     bigint references env.component,
  outcome     text not null check (outcome in ('better', 'worse', 'same', 'failed')),
  kpis        jsonb not null,           -- {kpi: {candidate, incumbent, target, higher_is_better}}
  cases       jsonb not null,           -- {held_out: n, labelled: n, card_tests: n}
  detail      jsonb not null default '{}',
  judge       text not null,
  login       text not null default session_user,
  at          timestamptz not null default now()
);
create function env.verdict_whole() returns trigger language plpgsql as $$
begin raise exception 'env: a verdict is kept whole'; end $$;
create trigger verdict_whole before update or delete on env.verdict for each row execute function env.verdict_whole();

-- A third of recorded signals are held out, by a hash of their id: the judge's cases, never an author's.
create function env.held_out(p_signal bigint) returns boolean language sql immutable as $$
  select ('x' || substr(md5('held-out:' || p_signal::text), 1, 8))::bit(32)::int % 3 = 0
$$;

-- What an author may read: the voice turns not held out, each heard utterance with what was said back.
create function env.training_turns(p_env text, p_limit int default 200)
returns table (heard_id bigint, heard text, heard_at timestamptz, said text, component bigint, stt_ms int,
               first_audio_ms int, turn_ms int, interrupted boolean, handed_off boolean)
language sql stable security definer set search_path = pg_catalog, public as $$
  select h.id, h.body->>'text', h.at, s.body->>'text', (s.body->>'component')::bigint, (h.body->>'stt_ms')::int,
         (s.body->>'first_audio_ms')::int, (s.body->>'turn_ms')::int, coalesce((s.body->>'interrupted')::boolean, false),
         coalesce((s.body->>'handoff') is not null and s.body->>'handoff' <> '', false)
    from env.signal h
    left join lateral (select * from env.signal x where x.key = p_env || '.voice.said' and x.id > h.id
                         and x.body->>'heard' = h.id::text order by x.id limit 1) s on true
   where h.key = p_env || '.voice.heard' and not env.held_out(h.id)
   order by h.id desc limit p_limit
$$;

-- An author submits a version; it is judged against the active one.
create function env.submit_component(p_env text, p_name text, p_card jsonb, p_author text) returns bigint
language plpgsql security definer set search_path = pg_catalog, public as $$
declare v int; inc bigint; cid bigint;
begin
  select coalesce(max(version), 0) + 1 into v from env.component where env = p_env and name = p_name;
  select id into inc from env.component where env = p_env and name = p_name and status = 'active';
  insert into env.component (env, name, version, card, status, against, author)
  values (p_env, p_name, v, p_card, 'proposed', inc, p_author) returning id into cid;
  perform env.publish(p_env || '.component.proposed', jsonb_build_object('component', cid, 'name', p_name, 'version', v,
                      'intent', p_card->>'intent', 'author', p_author), 'env');
  return cid;
end $$;

-- The judge takes the oldest proposed component (none: null).
create function env.claim_component() returns bigint language plpgsql security definer set search_path = pg_catalog, public as $$
declare cid bigint;
begin
  select id into cid from env.component where status = 'proposed' order by id limit 1 for update skip locked;
  if cid is not null then
    update env.component set status = 'judging', status_at = now(), status_by = session_user where id = cid;
  end if;
  return cid;
end $$;

-- The judge's verdict: kept whole; better leaves the component judged (a person may activate it), else refused.
create function env.record_verdict(p_component bigint, p_outcome text, p_kpis jsonb, p_cases jsonb, p_detail jsonb, p_judge text)
returns bigint language plpgsql security definer set search_path = pg_catalog, public as $$
declare c env.component; vid bigint;
begin
  select * into c from env.component where id = p_component for update;
  if c.status <> 'judging' then raise exception 'env: component % is %, not being judged', p_component, c.status; end if;
  insert into env.verdict (component, against, outcome, kpis, cases, detail, judge)
  values (p_component, c.against, p_outcome, p_kpis, p_cases, coalesce(p_detail, '{}'), p_judge) returning id into vid;
  update env.component set status = case when p_outcome = 'better' then 'judged' else 'refused' end,
         status_at = now(), status_by = p_judge where id = p_component;
  perform env.publish(c.env || '.component.judged', jsonb_build_object('component', p_component, 'name', c.name, 'version', c.version,
                      'outcome', p_outcome, 'verdict', vid, 'kpis', p_kpis), 'judge');
  return vid;
end $$;

-- A person makes a judged component the active one (the incumbent is retired); the first version of a component
-- may be made active with no verdict, as its seed.
create function env.activate(p_component bigint, p_person text) returns void language plpgsql as $$
declare c env.component;
begin
  select * into c from env.component where id = p_component for update;
  if c.id is null then raise exception 'env: no component %', p_component; end if;
  if not (c.status = 'judged' or (c.version = 1 and c.status = 'proposed')) then
    raise exception 'env: component % is %; only one the judge found better is activated', p_component, c.status;
  end if;
  update env.component set status = 'retired', status_at = now(), status_by = p_person
   where env = c.env and name = c.name and status = 'active';
  update env.component set status = 'active', status_at = now(), status_by = p_person where id = p_component;
  perform env.publish(c.env || '.component.activated', jsonb_build_object('component', p_component, 'name', c.name,
                      'version', c.version, 'by', p_person), 'env');
end $$;

create function env.active_component(p_env text, p_name text) returns table (id bigint, version int, card jsonb)
language sql stable security definer set search_path = pg_catalog, public as $$
  select id, version, card from env.component where env = p_env and name = p_name and status = 'active'
$$;

revoke all on all functions in schema env from public;
grant execute on function env.training_turns(text, int), env.submit_component(text, text, jsonb, text),
  env.active_component(text, text) to env_agent;

do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'env_judge') then
    create role env_judge nologin;
  end if;
end $$;
grant usage on schema env to env_judge;
grant select on env.signal, env.component, env.verdict to env_judge;
grant execute on function env.claim_component(), env.record_verdict(bigint, text, jsonb, jsonb, jsonb, text),
  env.held_out(bigint), env.active_component(text, text), env.publish(text, jsonb, text, jsonb),
  env.act(text, jsonb, text) to env_judge;
