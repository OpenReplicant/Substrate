-- Recall: one query over full-text, vectors and the graph (BRIEF.md section 6).
--
-- 1. wb.embedding gains `digest` (the text a vector was made from, hashed with its model), so a vector is made
--    again when its item's text or the model changes. Vectors are made outside Postgres (`workbench embed`, an
--    OpenAI-style embeddings endpoint): they are derived values, like the search index, not claims.
-- 2. api.recall(q, qvec, model, lim, depth, w_graph): three ranked lists, each optional, fused by reciprocal
--    rank (each list gives 1 / (k + rank)):
--      text    api.search's matches (any word, as a prefix)
--      vectors the items whose vector, made by `model`, is nearest `qvec` (cosine)
--      graph   items up to `depth` relations from the ten best of the first two, scored by the seeds they
--              hang from, halving per step
--    Everything is read as the caller: an item is in the result only if the caller can read it.

alter table wb.embedding add column if not exists digest text;

create or replace function wb.item_title(p_type text, p_id uuid) returns text
language plpgsql stable as $$
declare t text;
begin
  if not exists (select 1 from wb.content_type c where c.id = p_type) then
    return null;
  end if;
  execute format('select title from api.%I where id = $1', p_type) into t using p_id;
  return t;
exception when undefined_column then
  execute format('select null::text from api.%I where id = $1', p_type) into t using p_id;
  return coalesce(t, '');
end $$;

create or replace function wb.item_visible(p_type text, p_id uuid) returns boolean
language plpgsql stable as $$
declare ok boolean;
begin
  if not exists (select 1 from wb.content_type c where c.id = p_type) then
    return false;
  end if;
  execute format('select exists (select 1 from api.%I where id = $1)', p_type) into ok using p_id;
  return ok and wb.live(p_id);
end $$;

create or replace function api.recall(q text, qvec vector default null, model text default null, lim integer default 20,
                                      depth integer default 1, w_graph real default 1.0, k integer default 60)
returns table (type text, id uuid, title text, snippet text, score real, via text)
language plpgsql stable as $$
begin
  return query
  with recursive
  ft as (
    select s.type, s.id, max(s.rank) as best, (array_agg(s.snippet order by s.rank desc))[1] as snippet
      from api.search(q, 50) s
     where s.id is not null and wb.item_visible(s.type, s.id)
     group by s.type, s.id),
  ftr as (select ft.type, ft.id, ft.snippet, row_number() over (order by ft.best desc) as r from ft),
  vec as (
    select e.subject_type as type, e.subject_id as id, e.embedding <=> qvec as d
      from wb.embedding e
     where qvec is not null and e.model = recall.model
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
      from near n where wb.item_visible(n.type, n.id)
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

grant execute on function wb.item_title(text, uuid), wb.item_visible(text, uuid) to wb_viewer;
grant execute on function api.recall(text, vector, text, integer, integer, real, integer) to wb_viewer;
grant select on wb.embedding to wb_viewer;
