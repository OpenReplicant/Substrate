-- Recall can be limited to some content types (BRIEF.md section 6): api.recall gains `types`, a list of type ids; null
-- (the default) is every type, as before. The limit is applied to each list before it is cut, so asking for one type
-- ranks that type's items rather than the few of it among the best of everything (the text list reads up to 1000
-- matches instead of 50 when it is limited, the vector list takes the 200 nearest of those types). The graph walk still
-- starts from the limited hits, and what it reaches is limited too.

drop function api.recall(text, vector, text, integer, integer, real, integer);

create function api.recall(q text, qvec vector default null, model text default null, lim integer default 20,
                           depth integer default 1, w_graph real default 1.0, k integer default 60, types text[] default null)
returns table (type text, id uuid, title text, snippet text, score real, via text)
language plpgsql stable as $$
begin
  return query
  with recursive
  ft as (
    select s.type, s.id, max(s.rank) as best, (array_agg(s.snippet order by s.rank desc))[1] as snippet
      from api.search(q, case when types is null then 50 else 1000 end) s
     where s.id is not null and (types is null or s.type = any(types)) and wb.item_visible(s.type, s.id)
     group by s.type, s.id),
  ftr as (select ft.type, ft.id, ft.snippet, row_number() over (order by ft.best desc) as r from ft),
  vec as (
    select e.subject_type as type, e.subject_id as id, e.embedding <=> qvec as d
      from wb.embedding e
     where qvec is not null and e.model = recall.model and (types is null or e.subject_type = any(types))
     order by e.embedding <=> qvec
     limit 200),
  vecr as (
    select v.type, v.id, row_number() over (order by v.d) as r
      from vec v where wb.item_visible(v.type, v.id)
     limit 50),
  first as (
    select x.type, x.id, sum(x.s) as s, string_agg(x.via, '+' order by x.via) as via, max(x.snippet) as snippet
      from (select ftr.type, ftr.id, 1.0 / (k + ftr.r) as s, 'text' as via, ftr.snippet from ftr
            union all
            select vecr.type, vecr.id, 1.0 / (k + vecr.r), 'vector', null from vecr) x
     group by x.type, x.id),
  seeds as (select f.type, f.id, f.s from first f order by f.s desc limit 10),
  walk(type, id, s, hops, seen) as (
    select sd.type, sd.id, sd.s, 0, array[sd.id] from seeds sd where depth > 0
    union all
    select n.type, n.id, w.s / 2, w.hops + 1, w.seen || n.id
      from walk w
      join lateral (
        select r.to_type as type, r.to_id as id from wb.relation r where r.from_id = w.id
        union
        select r.from_type, r.from_id from wb.relation r where r.to_id = w.id) n on true
     where w.hops < depth and not n.id = any(w.seen)),
  near as (
    select w.type, w.id, sum(w.s) as s from walk w where w.hops > 0 group by w.type, w.id),
  nearr as (
    select n.type, n.id, row_number() over (order by n.s desc) as r
      from near n where (types is null or n.type = any(types)) and wb.item_visible(n.type, n.id)
     limit 50),
  fused as (
    select x.type, x.id, sum(x.s) as s, string_agg(distinct x.via, '+') as via, max(x.snippet) as snippet
      from (select f.type, f.id, f.s, unnest(string_to_array(f.via, '+')) as via, f.snippet from first f
            union all
            select nr.type, nr.id, w_graph / (k + nr.r), 'graph', null from nearr nr) x
     group by x.type, x.id)
  select fu.type, fu.id, wb.item_title(fu.type, fu.id), fu.snippet, fu.s::real, fu.via
    from fused fu
   order by fu.s desc
   limit lim;
end $$;

grant execute on function api.recall(text, vector, text, integer, integer, real, integer, text[]) to wb_viewer;
