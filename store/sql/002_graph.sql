-- The graph (S-135): pgGraph (1.2.1, Apache-2.0) straight over the store's own tables, nothing copied.
--
-- Node tables: store.entity and store.statement. A statement's `subject` edge goes both ways; its value edge
-- (value_entity) goes one way and is labelled with the statement's rank, so a path that follows only the
-- `subject`, `normal` and `preferred` edges follows statements in their direction and skips deprecated ones.
-- pgGraph's own triggers keep the built graph current as statements are written and ranked; store.project()
-- (scripts/db.py init) builds it, outside the transaction that registered it, as pgGraph requires.
--
-- One difference from store.usable: a normal statement outranked by a preferred one for the same subject and
-- property is still an edge, since pgGraph filters a row at a time and the best rank is a rule across rows.
-- The exact usable values are store.usable, store.render and expand.

create extension if not exists graph;

select graph.add_table('store.entity'::regclass, 'id', array['label', 'description']);
select graph.add_table('store.statement'::regclass, 'id', array['property', 'rank']);
select graph.add_edge('store.statement'::regclass, 'subject', 'store.entity'::regclass, 'id', 'subject', true);
select graph.add_edge('store.statement'::regclass, 'value_entity', 'store.entity'::regclass, 'id', 'value', false, null, 'rank');

-- The shortest path between two entities along statements that are not deprecated, in their direction: one
-- row per entity on it, with the statement and property that led there. pgGraph refuses an edge type no edge
-- has yet (no preferred statement with an entity value, say), so the ones it refuses are left out.
create function store.graph_path(p_from text, p_to text, p_max_depth int)
returns table (step int, node_table_name text, node_id text) language plpgsql stable as $$
declare kinds text[];
begin
  foreach kinds slice 1 in array array[array['subject', 'normal', 'preferred'], array['subject', 'normal', 'subject'],
                                       array['subject', 'preferred', 'subject'], array['subject', 'subject', 'subject']] loop
    begin
      return query select p.step::int, p.node_table_name::text, p.node_id::text
        from graph.shortest_path('store.entity'::regclass, p_from, 'store.entity'::regclass, p_to, p_max_depth, false, kinds) p;
      return;
    exception when invalid_parameter_value then
      null;
    end;
  end loop;
end $$;

create function store.path(p_from text, p_to text, p_max_depth int default 12)
returns table (step int, entity text, label text, via text, via_label text, statement uuid) language sql stable as $$
  with p as (
    select g.step, g.node_table_name as t, g.node_id as id, lag(g.node_id) over (order by g.step) as prev
    from store.graph_path(p_from, p_to, p_max_depth) g
  )
  select (row_number() over (order by p.step) - 1)::int, p.id, e.label, s.property, pr.label, s.id
  from p join store.entity e on e.id = p.id
       left join store.statement s on s.id::text = p.prev left join store.entity pr on pr.id = s.property
  where p.t = 'entity'
  order by p.step $$;
