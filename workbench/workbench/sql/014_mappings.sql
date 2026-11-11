-- Mappings from files (BRIEF.md section 2, "Terms"): a plugin's SSSOM TSV (`mappings:` in plugin.yaml) is loaded
-- into wb.mapping, CURIEs expanded against the file's curie_map, so subjects and objects are IRIs as in wb.term.
-- `plugin` says which plugin's file a row came from, so loading again replaces exactly that plugin's rows.

alter table wb.mapping add column if not exists plugin text;
alter table wb.mapping add column if not exists subject_label text;
alter table wb.mapping add column if not exists object_label text;
alter table wb.mapping add column if not exists comment text;
