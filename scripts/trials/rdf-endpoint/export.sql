-- Workbench's items, current claims and two kinds of relation as N-Triples, the same triples mapping.obda gives
-- Ontop virtually. Literals use to_json for escaping (JSON string escapes are valid N-Triples escapes here).
with item(t, cls, id, slug, title) as (
  select 'component', 'Component', id, slug, title from content.component
  union all select 'skill', 'Skill', id, slug, title from content.skill
  union all select 'hook', 'Hook', id, slug, title from content.hook
)
select format('<https://workbench.local/item/%s/%s> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <https://workbench.local/ns#%s> .', t, id, cls) from item
union all
select format('<https://workbench.local/item/%s/%s> <https://workbench.local/ns#slug> %s .', t, id, to_json(slug)) from item where slug is not null
union all
select format('<https://workbench.local/claim/%s> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <https://workbench.local/ns#Claim> .', c.id)
  from wb.claim c where c.status = 'current' and c.subject_type in ('component', 'skill', 'hook')
union all
select format('<https://workbench.local/claim/%s> <https://workbench.local/ns#about> <https://workbench.local/item/%s/%s> .', c.id, c.subject_type, c.subject_id)
  from wb.claim c where c.status = 'current' and c.subject_type in ('component', 'skill', 'hook')
union all
select format('<https://workbench.local/claim/%s> <https://workbench.local/ns#%s> %s .', c.id, p, to_json(v))
  from wb.claim c left join wb.source s on s.id = c.source_id,
       lateral (values ('field', c.field), ('quote', c.quote), ('author', c.author), ('sourceUri', s.uri)) x(p, v)
 where c.status = 'current' and c.subject_type in ('component', 'skill', 'hook') and v is not null
union all
select format('<https://workbench.local/item/%s/%s> <https://workbench.local/ns#%s> <https://workbench.local/item/%s/%s> .',
              from_type, from_id, predicate, to_type, to_id)
  from wb.relation where predicate in ('dependsOn', 'partOf');
