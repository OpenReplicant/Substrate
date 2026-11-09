#!/bin/sh
# The graph views, generated from Workbench's terms (spec step 7, workbench/workbench/graph.py): the Ontop mapping and
# ontology in .state/graph (the graph endpoint reloads them when they change), and pgGraph's projection. Run after
# a plugin's types or vocabulary change; scripts/up.sh runs it.
#
#   scripts/graph.sh
set -eu
. "$(dirname "$0")/lib.sh"

mkdir -p "$ROOT/.state/graph"
"$ROOT/scripts/workbench.sh" graph mapping "$ROOT/.state/graph" | python3 -c 'import json, sys; d = json.load(sys.stdin); print("  mapping:", d["mappings"], "mappings,", d["terms"], "terms;", ("changed " + ", ".join(d["changed"])) if d["changed"] else "unchanged")'
"$ROOT/scripts/workbench.sh" graph project | python3 -c 'import json, sys; d = json.load(sys.stdin); print("  pgGraph:", d.get("skipped") or "%(node_tables)s node tables, %(nodes)s nodes, %(edges)s edges" % d)'
