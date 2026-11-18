#!/bin/sh
# Kokoro on the GPU while the local model generates (S-150). Needs the stack up with the llm and voice profiles.
#   scripts/trials/voice-gpu/run.sh      -> .state/trials/voice-gpu/results.jsonl and summary.txt
set -eu
here=$(cd "$(dirname "$0")" && pwd); root=$(cd "$here/../../.." && pwd)
out=$root/.state/trials/voice-gpu; mkdir -p "$out"
podman cp "$here/contention.py" substrate-voice-1:/tmp/contention.py
podman exec substrate-voice-1 python3 /tmp/contention.py 2>/dev/null | grep '^{' > "$out/results.jsonl"
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader > "$out/gpu-memory.txt"
python3 "$here/summary.py" "$out/results.jsonl" | tee "$out/summary.txt"
