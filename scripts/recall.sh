#!/bin/sh
# Recall's vectors (S-83): the embedding model pulled into the local model server once, then every item whose
# text changed embedded again (workbench embed; nothing else is re-made). Run by up.sh, map.sh and observe.sh.
#
#   scripts/recall.sh              # pull the model if needed, then embed what is missing or stale
#   scripts/recall.sh "QUERY"      # ask recall: words, meaning and the graph in one ranking
set -eu
. "$(dirname "$0")/lib.sh"

model=$(env_value WORKBENCH_EMBED_MODEL)
[ -n "$model" ] || { echo "  recall: no embedding model set (WORKBENCH_EMBED_MODEL); words and the graph only"; exit 0; }
if [ $# -gt 0 ]; then
  exec "$ROOT/scripts/workbench.sh" recall "$*"
fi
name=${model#ollama/}
url="http://127.0.0.1:$(env_value OLLAMA_PORT)"
if ! curl -fsS "$url/api/tags" 2>/dev/null | python3 -c 'import json, sys; sys.exit(0 if sys.argv[1] in [m["name"] for m in json.load(sys.stdin)["models"]] else 1)' "$name"; then
  echo "  pulling $name into the local model server"
  curl -fsS "$url/api/pull" -d "{\"model\": \"$name\", \"stream\": false}" >/dev/null
fi
"$ROOT/scripts/workbench.sh" embed | python3 -c 'import json, sys; d = json.load(sys.stdin); print("  recall:", d["model"] + ":", d["items"], "items,", d["embedded"], "embedded,", d["dropped"], "dropped")'
