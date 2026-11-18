-- Components, roles, interfaces, catalogs and goals (S-139): how any thing, software or not, is taken apart into
-- parts, what each part does in its whole, what makes parts interchangeable, and what a change is judged on.
--
--   a whole   has part (P527) a part, qualified by object has role (P3831): the role the part plays there
--   a role    requires interface: what anything filling it must provide
--   a part    provides interface; a candidate from a catalog the same, with catalog id (qualified by catalog)
--             and described at URL (P973)
--   a whole   has goal: a goal has a metric and a target; a measurement (on a part or candidate) is qualified
--             by its goal and point in time (P585)
--   a verdict on a candidate, qualified by for role, against (the incumbent) and goal; its reference is the judge
--
-- store.alternatives(role): what provides every interface a role requires, beside what fills it now.
-- store.read_span: one span of a source, for a single quote (store.read_source reads a source whole).

select set_config('store.actor', 'store:migration 003', true);
select set_config('store.summary', 'components, roles, interfaces, catalogs and goals', true);

select store.new_entity('item', 'role', 'role', 'what a part does in its whole: a slot that another part providing the same interfaces could fill');
select store.new_entity('item', 'interface', 'interface', 'what a part provides and a role requires: a contract, an API, a fitting, a protocol, a shape');
select store.new_entity('item', 'goal', 'goal', 'something measurable a whole is meant to do better at');
select store.new_entity('item', 'catalog', 'catalog', 'a registry candidates come from (a package index, a vendor list, a parts book)');
select store.new_entity('item', 'better', 'verdict-better', 'a verdict: the candidate scored higher on the goal than what fills the role');
select store.new_entity('item', 'worse', 'verdict-worse', 'a verdict: the candidate scored lower on the goal');
select store.new_entity('item', 'no measurable difference', 'verdict-same', 'a verdict: no difference the judge could measure');
select store.new_entity('item', 'verdict', 'verdict-class', 'the class of verdicts');

select store.new_entity('property', 'has part', 'has-part', 'this whole has that part (Wikidata P527); qualify with object has role', 'item');
select store.new_entity('property', 'object has role', 'object-has-role', 'the role the value plays in this statement: the part''s role in its whole (Wikidata P3831)', 'item');
select store.new_entity('property', 'requires interface', 'requires-interface', 'anything filling this role must provide that interface', 'item');
select store.new_entity('property', 'provides interface', 'provides-interface', 'this part or candidate provides that interface', 'item');
select store.new_entity('property', 'catalog id', 'catalog-id', 'this candidate''s id in a catalog; qualify with catalog', 'external-id');
select store.new_entity('property', 'catalog', 'in-catalog', 'which catalog an id or a candidate is from', 'item');
select store.new_entity('property', 'described at URL', 'described-at-url', 'a page describing this (Wikidata P973)', 'url');
select store.new_entity('property', 'has goal', 'has-goal', 'this whole is judged on that goal', 'item');
select store.new_entity('property', 'metric', 'metric', 'how a goal is measured, in words a judge can apply', 'string');
select store.new_entity('property', 'target', 'target', 'the value a goal aims for', 'quantity');
select store.new_entity('property', 'measurement', 'measurement', 'a measured value; qualify with goal and point in time', 'quantity');
select store.new_entity('property', 'goal', 'for-goal', 'which goal a measurement or verdict is about', 'item');
select store.new_entity('property', 'point in time', 'point-in-time', 'when (Wikidata P585)', 'time');
select store.new_entity('property', 'verdict', 'verdict', 'a judge''s verdict on this candidate; qualify with for role, against and goal', 'item');
select store.new_entity('property', 'for role', 'for-role', 'the role a verdict or candidate is about', 'item');
select store.new_entity('property', 'against', 'against', 'what the candidate was compared with', 'item');

do $$
declare st uuid; q record;
begin
  for q in select * from (values ('verdict-better'), ('verdict-worse'), ('verdict-same')) v(subj) loop
    insert into store.statement (subject, property, value_entity)
    values (store.key(q.subj), store.key('instance-of'), store.key('verdict-class')) returning id into st;
    perform store.cite(st, 'parser', 'store:migration', null, '003');
  end loop;
  -- constraints: interfaces are interfaces, roles are roles, verdicts are verdicts
  for q in select * from (values ('requires-interface', 'interface'), ('provides-interface', 'interface'),
                                 ('object-has-role', 'role'), ('for-role', 'role'), ('verdict', 'verdict-class'),
                                 ('has-goal', 'goal'), ('for-goal', 'goal'), ('in-catalog', 'catalog')) v(prop, cls) loop
    insert into store.statement (subject, property, value_entity)
    values (store.key(q.prop), store.key('property-constraint'), store.key('value-type-constraint')) returning id into st;
    insert into store.qualifier (statement_id, ord, property, value_entity) values (st, 0, store.key('class'), store.key(q.cls));
    perform store.cite(st, 'parser', 'store:migration', null, '003');
  end loop;
end $$;

-- One span of a source, without reading the rest of it: kept if its text is the same, superseded if not.
create function store.read_span(p_uri text, p_locator text, p_text text, p_media_type text default null)
returns table (span_id uuid, change text) language plpgsql as $$
declare src uuid; cur record;
begin
  insert into store.source (uri, media_type) values (p_uri, p_media_type)
  on conflict (uri) do update set media_type = coalesce(excluded.media_type, store.source.media_type)
  returning id into src;
  select s.id, s.hash into cur from store.span s where s.source_id = src and s.locator = p_locator and s.superseded_at is null;
  if found and cur.hash = store.sha256(p_text) then
    span_id := cur.id; change := 'same'; return next; return;
  end if;
  if found then
    update store.span s set superseded_at = now() where s.id = cur.id;
    change := 'changed';
  else
    change := 'new';
  end if;
  insert into store.span (source_id, locator, text) values (src, p_locator, p_text) returning id into span_id;
  return next;
end $$;

-- What could fill a role: everything that provides every interface the role requires (none required: none
-- found), with whether it fills the role now, and in which whole.
create function store.alternatives(p_role text)
returns table (entity text, label text, fills_now boolean, in_whole text, provides text[]) language sql stable as $$
  with need as (
    select value_entity as iface from store.usable where subject = p_role and property = store.key('requires-interface')
  ), cand as (
    select u.subject, array_agg(distinct u.value_entity order by u.value_entity) as provides
    from store.usable u where u.property = store.key('provides-interface') group by u.subject
  ), filling as (
    select h.value_entity as part, h.subject as whole
    from store.usable h join store.qualifier q on q.statement_id = h.id
    where h.property = store.key('has-part') and q.property = store.key('object-has-role') and q.value_entity = p_role
  )
  select c.subject, e.label, exists (select 1 from filling f where f.part = c.subject),
         (select string_agg(f.whole, ', ' order by f.whole) from filling f where f.part = c.subject), c.provides
  from cand c join store.entity e on e.id = c.subject
  where exists (select 1 from need) and (select array_agg(iface) from need) <@ c.provides
  order by 3 desc, e.label $$;
