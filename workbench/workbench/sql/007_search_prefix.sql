-- Search for a palette: any word, as a prefix, and only the content's own text (not who made it).

create or replace function api.search(q text, lim integer default 20)
returns table (type text, id uuid, title text, snippet text, rank real, via text)
language plpgsql stable as $$
declare
  t      record;
  cols   text;
  query  tsquery;
begin
  -- any word, as a prefix ("kern ver" finds kernel and verdicts); quotes and punctuation are not syntax here
  select to_tsquery('english', string_agg(quote_literal(w) || ':*', ' | '))
    into query
    from regexp_split_to_table(lower(coalesce(q, '')), '[^[:alnum:]]+') w
   where w <> '';
  if query is null or query::text = '' then
    return;
  end if;
  for t in select ct.id from wb.content_type ct order by ct.id loop
    -- every text column of the type, as one document
    select string_agg(format('coalesce(%I, %L)', column_name, ''), ' || '' '' || ' order by ordinal_position)
      into cols
      from information_schema.columns
     where table_schema = 'content' and table_name = t.id and data_type = 'text'
       and column_name not in ('created_by', 'updated_by');
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
           (ts_rank(to_tsvector('english', c.quote), query) * 0.8)::real, 'quote:' || c.field
      from api.claims c
     where c.status = 'current' and c.quote is not null and to_tsvector('english', c.quote) @@ query
     order by 5 desc limit lim;
end $$;

