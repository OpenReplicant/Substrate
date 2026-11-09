-- Traversal as the caller (spec step 7): Workbench's roles may use pgGraph's functions, which apply the caller's
-- own rights to the rows a path passes through (graph.rls_mode = 'enforce', pgGraph's default).
grant usage on schema graph to wb_viewer;
