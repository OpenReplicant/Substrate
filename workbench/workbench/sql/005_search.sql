-- Recall (BRIEF.md section 2, W4): full-text search across every content type and every claim's quote, as
-- /api/rpc/search. It runs as the caller (security invoker), so it searches only what their role may read.
-- Vectors (pgvector, wb.embedding) come when an embedding model is chosen; this is the part that needs none.

create function api.search(q text, lim integer default 20)
returns table (type text, id uuid, title text, snippet text, rank real, via text)
language plpgsql stable as $$
declare
  t      record;
  cols   text;
  query  tsquery := websearch_to_tsquery('english', q);
begin
  if query is null or query::text = '' then
    return;
  end if;
  for t in select ct.id from wb.content_type ct order by ct.id loop
    -- every text column of the type, as one document
    select string_agg(format('coalesce(%I, %L)', column_name, ''), ' || '' '' || ' order by ordinal_position)
      into cols
      from information_schema.columns
     where table_schema = 'content' and table_name = t.id and data_type = 'text';
    if cols is null then
      continue;
    end if;
    return query execute format(
      'select %L::text, x.id, x.title, ts_headline(''english'', %s, $1, ''MaxFragments=1, MaxWords=18, MinWords=5''),
              ts_rank(to_tsvector(''english'', %s), $1), ''item''::text
         from api.%I x
        where to_tsvector(''english'', %s) @@ $1
        order by 5 desc limit $2', t.id, cols, cols, t.id, cols)
      using query, lim;
  end loop;
  -- what sources said: quotes on current claims
  return query
    select c.subject_type, c.subject_id, null::text,
           ts_headline('english', c.quote, query, 'MaxFragments=1, MaxWords=18, MinWords=5'),
           ts_rank(to_tsvector('english', c.quote), query) * 0.8, 'quote:' || c.field
      from api.claims c
     where c.status = 'current' and c.quote is not null and to_tsvector('english', c.quote) @@ query
     order by 5 desc limit lim;
end $$;

revoke execute on function api.search(text, integer) from public;
grant execute on function api.search(text, integer) to wb_viewer;
