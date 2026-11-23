-- The assistant's experience (S-178, S-180, S-182): one episode per model call the gate sees. System 1 is distilled
-- from it: skills (compiled responses with conditions) and preferences (which response fits which scenario, TabICL
-- over episodes). docs/privacy.md: P6 is loosened for this store only, on the owner's word: the owner's words are
-- kept, encrypted at rest; deletion of one episode, a time range or all; a retention period.
--
--   experience  an episode: the scenario (the request, encrypted; its features and embedding), the response (who
--               answered: a skill or a rung; what it said, encrypted; what it depended on), how the gate decided
--               (the decider's probabilities, the impasse when it handed the call on). Kept whole; only deleted.
--   outcome     how an episode turned out, attached later by the episode's ref (long-horizon feedback): `ok` (was the
--               response right, true or false), `correct` (the responder that should have answered), `score` (0 to
--               1). Many per episode, never changed; a note, if any, encrypted like the text.
--
-- The text is encrypted with pgcrypto's pgp_sym_encrypt under a key the database never stores: the writer passes it
-- as a bound parameter (EXPERIENCE_KEY in .env), and only the owner's functions decrypt.
--
-- Who may do what (the functions run as their owner; execute is granted by name):
--   env_gate    (the gate's login) records an episode; reads episodes for its decider's context, without the text;
--               adds outcomes
--   env_agent   (the assistant's and the voice front end's logins) adds outcomes to an episode it knows the ref of
--   the owner   reads the text, deletes, sets the retention (env.set('experience', 'retention_days', '30', 'owner'))

create extension if not exists pgcrypto;
create extension if not exists vector;

create table env.experience (
  id           bigserial primary key,
  ref          uuid not null unique default gen_random_uuid(),   -- what outcomes and callers refer to
  at           timestamptz not null default now(),
  caller       text not null check (caller <> ''),               -- the gateway caller the call came from
  login        text not null default session_user,
  request      bytea not null,                                   -- the scenario's text (messages as JSON), encrypted
  features     jsonb not null default '{}' check (jsonb_typeof(features) = 'object'),
  embedder     text,
  embedding    vector,
  responder    text not null check (responder ~ '^(skill:[a-z0-9_.-]+|fast|slow|cloud|model:[a-z0-9_./:-]+)$'),
  response     bytea,                                            -- what was answered, encrypted
  depended_on  jsonb not null default '[]' check (jsonb_typeof(depended_on) = 'array'),
  decision     jsonb not null default '{}' check (jsonb_typeof(decision) = 'object'),
  impasse      text check (impasse in ('none', 'tie', 'low'))    -- null: System 1 answered or routed with confidence
);
create index experience_at on env.experience (at);
create index experience_caller on env.experience (caller, at);

create table env.outcome (
  id        bigserial primary key,
  episode   bigint not null references env.experience on delete cascade,
  kind      text not null check (kind in ('ok', 'correct', 'score')),
  value     jsonb not null,
  source    text not null check (source <> ''),                  -- who said so: owner, scorer, task, ...
  note      bytea,                                               -- encrypted, optional
  login     text not null default session_user,
  at        timestamptz not null default now(),
  check ((kind = 'ok' and jsonb_typeof(value) = 'boolean')
      or (kind = 'correct' and jsonb_typeof(value) = 'string')
      or (kind = 'score' and jsonb_typeof(value) = 'number' and (value::text)::numeric between 0 and 1))
);
create index outcome_episode on env.outcome (episode);

-- Kept whole: an episode or an outcome is never changed. Deleting is the owner's (forget, expire), and only through
-- them: a login that may record may not delete.
create function env.experience_whole() returns trigger language plpgsql as $$
begin
  if tg_op = 'DELETE' and current_setting('env.forgetting', true) = 'on' then
    return old;
  end if;
  raise exception 'env: experience is kept whole; only the owner forgets it';
end $$;
create trigger experience_whole before update or delete on env.experience for each row execute function env.experience_whole();
create trigger outcome_whole before update or delete on env.outcome for each row execute function env.experience_whole();

create function env.record_episode(p_key text, p_caller text, p_request text, p_features jsonb, p_embedder text,
                                   p_embedding vector, p_responder text, p_response text, p_depended_on jsonb,
                                   p_decision jsonb, p_impasse text)
returns uuid language plpgsql security definer set search_path = pg_catalog, public as $$
declare r uuid;
begin
  if coalesce(p_key, '') = '' then raise exception 'env: experience needs its key'; end if;
  insert into env.experience (caller, login, request, features, embedder, embedding, responder, response,
                              depended_on, decision, impasse)
  values (p_caller, session_user, pgp_sym_encrypt(p_request, p_key), coalesce(p_features, '{}'), p_embedder,
          p_embedding, p_responder, case when p_response is null then null else pgp_sym_encrypt(p_response, p_key) end,
          coalesce(p_depended_on, '[]'), coalesce(p_decision, '{}'), p_impasse)
  returning ref into r;
  return r;
end $$;

create function env.add_outcome(p_ref uuid, p_kind text, p_value jsonb, p_source text, p_note text default null,
                                p_key text default null)
returns bigint language plpgsql security definer set search_path = pg_catalog, public as $$
declare e bigint; o bigint;
begin
  select id into e from env.experience where ref = p_ref;
  if e is null then raise exception 'env: no episode %', p_ref; end if;
  if p_note is not null and coalesce(p_key, '') = '' then raise exception 'env: a note needs the key'; end if;
  insert into env.outcome (episode, kind, value, source, note, login)
  values (e, p_kind, p_value, p_source, case when p_note is null then null else pgp_sym_encrypt(p_note, p_key) end,
          session_user)
  returning id into o;
  return o;
end $$;

-- The decider's context: episodes with their latest outcome of each kind, newest first, without any text.
create function env.episodes(p_caller text default null, p_since timestamptz default null, p_limit int default 5000)
returns table (ref uuid, at timestamptz, caller text, features jsonb, embedder text, embedding vector,
               responder text, decision jsonb, impasse text, ok boolean, correct text, score numeric, outcomes int)
language sql stable security definer set search_path = pg_catalog, public as $$
  select e.ref, e.at, e.caller, e.features, e.embedder, e.embedding, e.responder, e.decision, e.impasse,
         (select (o.value)::text::boolean from env.outcome o where o.episode = e.id and o.kind = 'ok' order by o.at desc, o.id desc limit 1),
         (select o.value #>> '{}' from env.outcome o where o.episode = e.id and o.kind = 'correct' order by o.at desc, o.id desc limit 1),
         (select (o.value)::text::numeric from env.outcome o where o.episode = e.id and o.kind = 'score' order by o.at desc, o.id desc limit 1),
         (select count(*)::int from env.outcome o where o.episode = e.id)
  from env.experience e
  where (p_caller is null or e.caller = p_caller) and (p_since is null or e.at >= p_since)
  order by e.at desc, e.id desc
  limit greatest(p_limit, 0)
$$;

-- The owner's: the text back, with the key (a wrong key fails in pgcrypto).
create function env.episode_text(p_ref uuid, p_key text)
returns table (request text, response text)
language sql stable security definer set search_path = pg_catalog, public as $$
  select pgp_sym_decrypt(request, p_key), case when response is null then null else pgp_sym_decrypt(response, p_key) end
  from env.experience where ref = p_ref
$$;

-- The owner's: forget one episode, a time range, or everything (P9). Outcomes go with their episode; nothing else is
-- derived and stored (the decider's context is read fresh). Outcomes are removed by the cascade. Returns the number of episodes deleted.
create function env.forget_experience(p_ref uuid default null, p_from timestamptz default null,
                                      p_to timestamptz default null, p_all boolean default false)
returns int language plpgsql security definer set search_path = pg_catalog, public as $$
declare n int;
begin
  if p_ref is null and p_from is null and p_to is null and not p_all then
    raise exception 'env: say what to forget (an episode, a time range, or all)';
  end if;
  perform set_config('env.forgetting', 'on', true);
  delete from env.experience e
   where p_all or e.ref = p_ref
      or ((p_from is not null or p_to is not null) and e.at >= coalesce(p_from, '-infinity') and e.at < coalesce(p_to, 'infinity'));
  get diagnostics n = row_count;
  perform set_config('env.forgetting', 'off', true);
  return n;
end $$;

-- The owner's: drop what is older than the retention (P7), the setting `experience.retention_days` (none: keep).
create function env.expire_experience() returns int language plpgsql security definer set search_path = pg_catalog, public as $$
declare d numeric;
begin
  select (value #>> '{}')::numeric into d from env.setting where env = 'experience' and name = 'retention_days'
   order by id desc limit 1;
  if d is null or d <= 0 then return 0; end if;
  return env.forget_experience(p_to => now() - make_interval(secs => d * 86400));
end $$;

revoke all on env.experience, env.outcome from public;
revoke all on function env.record_episode(text, text, text, jsonb, text, vector, text, text, jsonb, jsonb, text),
  env.add_outcome(uuid, text, jsonb, text, text, text), env.episodes(text, timestamptz, int),
  env.episode_text(uuid, text), env.forget_experience(uuid, timestamptz, timestamptz, boolean),
  env.expire_experience() from public;

do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'env_gate') then
    create role env_gate nologin;
  end if;
end $$;
grant usage on schema env to env_gate;
grant execute on function env.record_episode(text, text, text, jsonb, text, vector, text, text, jsonb, jsonb, text),
  env.add_outcome(uuid, text, jsonb, text, text, text), env.episodes(text, timestamptz, int) to env_gate;
grant execute on function env.add_outcome(uuid, text, jsonb, text, text, text) to env_agent;
