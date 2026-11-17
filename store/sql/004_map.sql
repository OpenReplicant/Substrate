-- A map as a graph (S-139), for the UI's map diagram and the agent: a whole, its parts to any depth with the role
-- each plays, the interfaces roles require and parts provide, and what else could fill each role.
--
--   store.map(whole, depth) -> edges: source, target, kind, statement (null for a derived edge), flagged
--     has-part    whole -> part          (usable has part statements, recursively to depth)
--     plays       part  -> role          (the has part statement's object has role qualifier)
--     requires    role  -> interface
--     provides    part  -> interface     (and a candidate's)
--     could-fill  candidate -> role      (store.alternatives: provides every interface the role requires, fills
--                                         no role in this map)
--   store.map_nodes(whole, depth) -> id, label, description, kind (whole, part, role, interface, candidate)
--
-- Only usable statements (preferred, else normal) are followed, so a deprecated part drops out of the map.

select set_config('store.actor', 'store:migration 004', true);

create function store.map(p_whole text, p_depth int default 6)
returns table (source text, target text, kind text, statement uuid, flagged boolean) language sql stable as $$
  with recursive part (whole, part, st, depth) as (
    select h.subject, h.value_entity, h.id, 1 from store.usable h
    where h.subject = p_whole and h.property = store.key('has-part') and h.value_entity is not null
    union
    select h.subject, h.value_entity, h.id, p.depth + 1 from part p join store.usable h on h.subject = p.part
    where h.property = store.key('has-part') and h.value_entity is not null and p.depth < p_depth
  ), plays as (
    select p.part, q.value_entity as role, p.st from part p join store.qualifier q on q.statement_id = p.st
    where q.property = store.key('object-has-role') and q.value_entity is not null
  ), holder as (                                     -- everything that can provide an interface: the whole and its parts
    select p_whole as e union select part from part
  ), role as (select distinct role from plays),
  cand as (
    select a.entity, r.role from role r, store.alternatives(r.role) a
    where a.entity not in (select e from holder)
  ), edge as (
    select whole, part, 'has-part', st from part
    union all select part, role, 'plays', null::uuid from plays
    union all select u.subject, u.value_entity, 'requires', u.id from store.usable u
      where u.property = store.key('requires-interface') and u.subject in (select role from role)
    union all select u.subject, u.value_entity, 'provides', u.id from store.usable u
      where u.property = store.key('provides-interface')
        and (u.subject in (select e from holder) or u.subject in (select entity from cand))
    union all select entity, role, 'could-fill', null::uuid from cand
  )
  select distinct e.*, exists (select 1 from store.flag f where f.statement_id = e.st) from edge e $$;

create function store.map_nodes(p_whole text, p_depth int default 6)
returns table (id text, label text, description text, kind text) language sql stable as $$
  with m as (select * from store.map(p_whole, p_depth)),
  n as (select p_whole as id union select source from m union select target from m)
  select n.id, e.label, e.description,
         case when n.id = p_whole then 'whole'
              when exists (select 1 from m where m.target = n.id and m.kind in ('plays', 'could-fill')) then 'role'
              when exists (select 1 from m where m.target = n.id and m.kind in ('requires', 'provides')) then 'interface'
              when exists (select 1 from m where m.source = n.id and m.kind = 'could-fill') then 'candidate'
              else 'part' end
  from n join store.entity e on e.id = n.id order by 1 $$;
