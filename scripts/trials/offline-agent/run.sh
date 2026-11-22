#!/bin/sh
# Offline-agent trial (S-162). Usage: VENVS=<dir with own/ pai/ oai/ venvs> sh scripts/trials/offline-agent/run.sh
# Starts the stub model server and a recording proxy, runs each candidate on each case, writes one line per
# candidate and case to .state/trials/offline-agent/summary.txt.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../../.." && pwd)
VENVS=${VENVS:?directory holding the venvs own, pai, oai}
out=$root/.state/trials/offline-agent
mkdir -p "$out"; : > "$out/summary.txt"
LLM_PORT=18771; PROXY_PORT=18772
export STUB_LOG=$out/stub_calls.jsonl PROXY_LOG=$out/proxy_hits.log
python3 "$here/stub_llm.py" $LLM_PORT & p1=$!
python3 "$here/proxy_rec.py" $PROXY_PORT & p2=$!
trap 'kill $p1 $p2 2>/dev/null' EXIT
sleep 1
for cand in own pai oai; do
  for case in tool veto; do
    : > "$STUB_LOG"; : > "$PROXY_LOG"
    line=$(cd "$here" && HTTPS_PROXY=http://127.0.0.1:$PROXY_PORT HTTP_PROXY=http://127.0.0.1:$PROXY_PORT \
      https_proxy=http://127.0.0.1:$PROXY_PORT http_proxy=http://127.0.0.1:$PROXY_PORT NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost OPENAI_API_KEY=stub-key \
      "$VENVS/$cand/bin/python" run_case.py $cand $case http://127.0.0.1:$LLM_PORT/v1 "$VENVS/$cand/bin/python" "$here/stub_mcp.py" 2>"$out/$cand-$case.err" | tail -1)
    calls=$(wc -l < "$STUB_LOG"); hits=$(sort -u "$PROXY_LOG" | tr '\n' ',' )
    size=$(du -sm "$VENVS/$cand/lib/python3"*/site-packages | cut -f1)
    pkgs=$(ls -d "$VENVS/$cand"/lib/python3*/site-packages/*.dist-info | wc -l)
    echo "$cand case=$case stub_model_calls=$calls extra_network=[${hits}] install_mb=$size dists=$pkgs run=$line" | tee -a "$out/summary.txt"
  done
done
