#!/bin/sh
# The voice head's trial (plan step 5): every candidate on the same cases, each in its own process, on the CPU
# (TRIAL_THREADS, 4) except Kokoro-FastAPI's GPU image. Output: .state/trials/voice-head/ (results.jsonl, the clips).
#
#   scripts/trials/voice-head/run.sh
set -eu
here=$(cd "$(dirname "$0")" && pwd); root=$(cd "$here/../../.." && pwd)
out=$root/.state/trials/voice-head; mkdir -p "$out/models"; rm -rf "$out/tts" "$out/results.jsonl"
img=substrate-trial-voice:local
podman build -q -t $img "$here" >/dev/null
run() { f=$1; shift; podman run --rm --network host -e TRIAL_THREADS -e KOKORO_URL -v "$here:/code:Z" -v "$out:/out:Z" $img python3 -I "/code/$f" "$@"; }
run fetch.py /out/models
# Kokoro-FastAPI on the GPU: the owner's own copy of ghcr.io/remsky/kokoro-fastapi-gpu:latest (v0.10.0, built
# 2026-11-08), copied from Docker into Podman (docker save | podman load) and checked by its image id
KOKORO_IMAGE=ghcr.io/remsky/kokoro-fastapi-gpu:latest
KOKORO_ID=sha256:fed40d86539c
case "$(podman image inspect -f '{{.Id}}' "$KOKORO_IMAGE" 2>/dev/null)" in "${KOKORO_ID#sha256:}"*) ;; *) echo "$KOKORO_IMAGE is not image ${KOKORO_ID}" >&2; exit 1 ;; esac
podman rm -f trial-kokoro >/dev/null 2>&1 || true
lib=${NVIDIA_LIB_DIR:-/usr/lib/x86_64-linux-gnu}
# the GPU as deploy/compose.nvidia.yaml gives it to Ollama: device nodes and the driver's libraries, no CDI, no root
podman run -d --name trial-kokoro -p 127.0.0.1:8880:8880 \
  --device /dev/nvidia0 --device /dev/nvidiactl --device /dev/nvidia-uvm --device /dev/nvidia-uvm-tools \
  -v "$lib/libcuda.so.1:/usr/lib/x86_64-linux-gnu/libcuda.so.1:ro" -v "$lib/libcuda.so.1:/usr/lib/x86_64-linux-gnu/libcuda.so:ro" \
  -v "$lib/libnvidia-ml.so.1:/usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1:ro" \
  -v "$lib/libnvidia-ptxjitcompiler.so.1:/usr/lib/x86_64-linux-gnu/libnvidia-ptxjitcompiler.so.1:ro" \
  "$KOKORO_IMAGE" >/dev/null
for c in tts:sherpa-kokoro tts:kokoro-onnx; do run trial.py /out/models /out "$c"; done
# Kokoros (Rust; the owner's local image kokoros:latest, built 2025-08-07, id 520ad512e693): its OpenAI-style server on the CPU
podman rm -f trial-kokoros >/dev/null 2>&1 || true
podman run -d --name trial-kokoros -p 127.0.0.1:3000:3000 docker.io/library/kokoros:latest openai >/dev/null
for i in $(seq 60); do curl -s -o /dev/null http://127.0.0.1:3000/ && break; sleep 2; done
run trial.py /out/models /out tts:kokoros || echo '{"candidate": "tts:kokoros", "case": "failed"}' >> "$out/results.jsonl"
podman rm -f trial-kokoros >/dev/null
for i in $(seq 120); do curl -sf http://127.0.0.1:8880/health >/dev/null 2>&1 && break; sleep 2; done
run trial.py /out/models /out tts:kokoro-fastapi-gpu || echo '{"candidate": "tts:kokoro-fastapi-gpu", "case": "failed"}' >> "$out/results.jsonl"
podman logs trial-kokoro 2>&1 | grep -i -E 'cuda|gpu|device|error' | head -8 > "$out/kokoro-fastapi.log" || true
podman rm -f trial-kokoro >/dev/null
for c in stt:sherpa-parakeet-110m stt:sherpa-parakeet-v3 stt:onnx-asr-parakeet-v3; do run trial.py /out/models /out "$c"; done
run summary.py /out/results.jsonl /out/models | tee "$out/summary.txt"
