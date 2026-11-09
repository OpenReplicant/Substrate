#!/usr/bin/env bash
# Spec step 4's trial: four RDF/SPARQL candidates against Workbench's real tables (docs/choices/rdf-endpoint.md).
# Each answers the same three queries; Ontop reads Postgres live, the others load an export. Then a relation is
# added for a moment (and removed) to see who answers from current data. Output: one line per candidate and query,
# and .state/trials/rdf-endpoint/results.jsonl.
#   scripts/trials/rdf-endpoint/run.sh [ontop fuseki oxigraph rdflib]
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../../.." && pwd)"
# a setting through lib.sh, which finds the repository from its caller's path ($0 in scripts/)
setting() { sh -c '. "$(dirname "$0")/lib.sh"; env_value "$1"' "$root/scripts/run.sh" "$1"; }
eng="${CONTAINER_ENGINE:-podman}"
work="$root/.state/trials/rdf-endpoint"
mkdir -p "$work/jars"
out="$work/results.jsonl"
: > "$out"
net=substrate_default
db_container=substrate-db-1

ONTOP_IMAGE=docker.io/ontop/ontop:5.5.0
OXIGRAPH_IMAGE=ghcr.io/oxigraph/oxigraph:0.5.13
JAVA_IMAGE=docker.io/library/eclipse-temurin:21-jre
PYTHON_IMAGE=docker.io/library/python:3.13-slim
PG_JDBC=org/postgresql/postgresql/42.7.14/postgresql-42.7.14.jar
FUSEKI_JAR=org/apache/jena/jena-fuseki-server/6.2.0/jena-fuseki-server-6.2.0.jar
RDFLIB=rdflib==7.6.0
OWLRL=owlrl==7.6.2

psql_wb() { "$eng" exec -i "$db_container" psql -U postgres -d workbench -At "$@"; }

jar() {  # fetch a jar from Maven Central once, checking its published sha1
  local path="$1" file="$work/jars/$(basename "$1")"
  if [ ! -f "$file" ]; then
    curl -fsSL -o "$file.tmp" "https://repo1.maven.org/maven2/$path"
    local want; want="$(curl -fsSL "https://repo1.maven.org/maven2/$path.sha1" | cut -c1-40)"
    [ "$(sha1sum "$file.tmp" | cut -c1-40)" = "$want" ] || { echo "sha1 mismatch: $path" >&2; exit 1; }
    mv "$file.tmp" "$file"
  fi
  printf '%s' "$file"
}

record() { printf '%s\n' "$1" >> "$out"; printf '  %s\n' "$1"; }

sparql() {  # sparql URL FILE -> JSON results
  curl -fsS --max-time 60 -H 'Accept: application/sparql-results+json' --data-urlencode "query@$2" "$1"
}

summary() {  # the first value of the first row, or the row count, from SPARQL JSON results
  python3 -c '
import json, sys
r = json.load(sys.stdin)["results"]["bindings"]
if len(r) == 1 and len(r[0]) == 1:
    print(next(iter(r[0].values()))["value"])
else:
    print(len(r))'
}

wait_for() {  # wait_for URL SECONDS
  local i
  for i in $(seq "$2"); do curl -fsS -o /dev/null --max-time 2 "$1" 2>/dev/null && return 0; sleep 1; done
  return 1
}

mem() { "$eng" stats --no-stream --format '{{.MemUsage}}' "$1" 2>/dev/null | cut -d/ -f1 | tr -d ' '; }

# a moment's extra relation, removed again: does the endpoint see current data?
probe_add() {
  psql_wb -c "insert into wb.relation (from_type, from_id, predicate, to_type, to_id)
              select 'component', a.id, 'dependsOn', 'component', b.id from content.component a, content.component b
              where a.slug = 'front-door' and b.slug = 'postgres' on conflict do nothing returning from_id" >/dev/null
}
probe_remove() {
  psql_wb -c "delete from wb.relation r using content.component a, content.component b
              where r.from_id = a.id and r.to_id = b.id and r.predicate = 'dependsOn'
              and a.slug = 'front-door' and b.slug = 'postgres'" >/dev/null
}
trap probe_remove EXIT

endpoint_trial() {  # endpoint_trial NAME URL CONTAINER STARTED_AT
  local name="$1" url="$2" ctr="$3" started="$4" q n before after
  record "{\"candidate\":\"$name\",\"ready_s\":$(( $(date +%s) - started )),\"mem\":\"$(mem "$ctr")\"}"
  for q in "$here"/q*.rq; do
    n="$(sparql "$url" "$q" | summary)" || n="error"
    record "{\"candidate\":\"$name\",\"query\":\"$(basename "$q")\",\"answer\":\"$n\"}"
  done
  before="$(sparql "$url" "$here/q3-related.rq" | summary)"
  probe_add; after="$(sparql "$url" "$here/q3-related.rq" | summary)"; probe_remove
  record "{\"candidate\":\"$name\",\"fresh\":$([ "$after" != "$before" ] && echo true || echo false),\"before\":\"$before\",\"after\":\"$after\"}"
}

expected() {
  local parts rel
  parts="$(psql_wb -c "select (select count(*) from content.component) + (select count(*) from content.skill) + (select count(*) from content.hook)")"
  rel="$(psql_wb -c "select count(*) from wb.relation where predicate in ('dependsOn', 'partOf')")"
  record "{\"expected\":{\"q1-parts.rq\":\"$parts\",\"q3-related.rq\":\"$rel\"}}"
}

export_data() { psql_wb < "$here/export.sql" > "$work/data.nt"; cp "$here/vocab.ttl" "$here"/q*.rq "$work/"; }

trial_ontop() {
  local jdbc; jdbc="$(jar "$PG_JDBC")"
  "$eng" rm -f trial-ontop >/dev/null 2>&1 || true
  local t; t=$(date +%s)
  ONTOP_DB_PASSWORD="$(setting POSTGRES_PASSWORD)" "$eng" run -d --name trial-ontop --network "$net" -p 127.0.0.1:18081:8080 \
    -v "$jdbc:/opt/ontop/jdbc/postgresql.jar:ro,Z" -v "$here:/trial:ro,Z" \
    -e ONTOP_MAPPING_FILE=/trial/mapping.obda -e ONTOP_ONTOLOGY_FILE=/trial/vocab.ttl \
    -e ONTOP_DB_URL=jdbc:postgresql://db:5432/workbench -e ONTOP_DB_USER=postgres -e ONTOP_DB_PASSWORD \
    -e ONTOP_DB_DRIVER=org.postgresql.Driver -e ONTOP_LOG_LEVEL=warn "$ONTOP_IMAGE" >/dev/null
  wait_for "http://127.0.0.1:18081/sparql?query=ASK%7B%7D" 120 || { "$eng" logs --tail 20 trial-ontop; return 1; }
  endpoint_trial ontop http://127.0.0.1:18081/sparql trial-ontop "$t"
  "$eng" rm -f trial-ontop >/dev/null
}

trial_fuseki() {
  local fj; fj="$(jar "$FUSEKI_JAR")"
  "$eng" rm -f trial-fuseki >/dev/null 2>&1 || true
  local t; t=$(date +%s)
  "$eng" run -d --name trial-fuseki -p 127.0.0.1:18082:3030 -v "$fj:/fuseki.jar:ro,Z" -v "$work:/w:ro,Z" \
    "$JAVA_IMAGE" java -jar /fuseki.jar --file=/w/data.nt --rdfs=/w/vocab.ttl /ds >/dev/null
  wait_for "http://127.0.0.1:18082/ds/sparql?query=ASK%7B%7D" 120 || { "$eng" logs --tail 20 trial-fuseki; return 1; }
  endpoint_trial fuseki http://127.0.0.1:18082/ds/sparql trial-fuseki "$t"
  "$eng" rm -f trial-fuseki >/dev/null
}

trial_oxigraph() {
  "$eng" rm -f trial-oxigraph >/dev/null 2>&1 || true
  local t; t=$(date +%s)
  "$eng" run -d --name trial-oxigraph -p 127.0.0.1:18083:7878 "$OXIGRAPH_IMAGE" serve --location /data --bind 0.0.0.0:7878 >/dev/null
  wait_for "http://127.0.0.1:18083/query?query=ASK%7B%7D" 60 || { "$eng" logs --tail 20 trial-oxigraph; return 1; }
  curl -fsS -X POST -H 'Content-Type: application/n-triples' --data-binary "@$work/data.nt" "http://127.0.0.1:18083/store?default"
  curl -fsS -X POST -H 'Content-Type: text/turtle' --data-binary "@$work/vocab.ttl" "http://127.0.0.1:18083/store?default"
  endpoint_trial oxigraph http://127.0.0.1:18083/query trial-oxigraph "$t"
  "$eng" rm -f trial-oxigraph >/dev/null
}

trial_rdflib() {
  local line
  while IFS= read -r line; do record "{\"candidate\":\"rdflib+owlrl\",${line#\{}"; done < <(
    "$eng" run --rm -v "$work:/w:ro,Z" -v "$here/rdflib_trial.py:/trial.py:ro,Z" "$PYTHON_IMAGE" \
      sh -c "pip install -q --disable-pip-version-check --root-user-action=ignore $RDFLIB $OWLRL >/dev/null && python /trial.py /w")
  record "{\"candidate\":\"rdflib+owlrl\",\"fresh\":false,\"note\":\"in-process graph from an export; current data means rebuilding it\"}"
}

expected
export_data
for c in "${@:-ontop fuseki oxigraph rdflib}"; do
  for one in $c; do echo "== $one"; "trial_$one" || record "{\"candidate\":\"$one\",\"failed\":true}"; done
done
