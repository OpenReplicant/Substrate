-- The old assistant retired (S-194): it starts again from scratch, so what it left in the environment goes. Its data
-- was dumped first (.state/backups/substrate-env-pgmq-20261123-125241.sql). What stays is the environment itself
-- (005, 006): signals, subscribers, actuators behind gates, actions, settings.
--
--   007's components and verdicts (the judge of S-151, which Morphogen replaces) and 008's experience (the ladder's
--   episodes and outcomes, S-183): their tables and functions
--   every actuator and subscriber queue the companion, the worker and the blocks registered, with their actions,
--   settings, readers and topic bindings
--   the logins companion, worker and judge, and the role env_judge

drop table if exists env.outcome, env.experience, env.verdict, env.component cascade;
do $$
declare f regprocedure;
begin
  for f in select p.oid::regprocedure from pg_proc p where p.pronamespace = 'env'::regnamespace and p.proname = any (
      array['experience_whole', 'record_episode', 'add_outcome', 'episodes', 'episode_text', 'forget_experience',
            'expire_experience', 'verdict_whole', 'held_out', 'training_turns', 'submit_component', 'claim_component',
            'record_verdict', 'activate', 'active_component']) loop
    execute format('drop function %s cascade', f);
  end loop;
end $$;

do $$
declare q text;
begin
  for q in select queue from env.actuator where name ~ '^(companion|worker|blocks)\.'
           union select unnest(array['companion_session', 'worker_loop']) loop
    delete from pgmq.topic_bindings where queue_name = q;
    delete from env.reader where queue = q;
    if exists (select 1 from pgmq.meta where queue_name = q) then
      perform pgmq.drop_queue(q);
    end if;
  end loop;
end $$;
delete from env.setting where action in (select id from env.action where actuator ~ '^(companion|worker|blocks)\.')
                           or env in ('companion', 'worker', 'voice');
delete from env.action where actuator ~ '^(companion|worker|blocks)\.';
delete from env.actuator where name ~ '^(companion|worker|blocks)\.';

do $$
declare r text;
begin
  foreach r in array array['companion', 'worker', 'judge', 'env_judge'] loop
    if exists (select 1 from pg_roles where rolname = r) then
      execute format('drop owned by %I', r);
      execute format('drop role %I', r);
    end if;
  end loop;
end $$;
