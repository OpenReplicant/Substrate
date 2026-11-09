-- A relation says who stated it, like a claim: the extractor (or person) and the run and source it came from.
-- An extractor's run replaces only the relations it stated before, so two extractors can relate the same item
-- without one erasing the other. Relations from before this migration have no author; the next run of any
-- extractor that relates from the same item replaces them.

alter table wb.relation add column author text;
alter table wb.relation add column run uuid;
alter table wb.relation add column source uuid;
alter table wb.relation drop constraint relation_from_type_from_id_predicate_to_type_to_id_key;
create unique index relation_by_author on wb.relation (from_type, from_id, predicate, to_type, to_id, coalesce(author, ''));
create index relation_to on wb.relation (to_type, to_id);

create or replace view api.relations with (security_invoker = true) as
  select id, from_type, from_id, predicate, to_type, to_id, created_at, author, run, source from wb.relation;
grant select on api.relations to wb_viewer;
