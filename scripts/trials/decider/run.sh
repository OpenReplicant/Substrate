#!/bin/sh
# The decider trial (S-178): stage 1 in the voice head's container (the gateway), stage 2 in the trial image.
# scripts/trials/decider/run.sh [stage2-decider ...]   (no names: all; output in .state/trials/decider/)
set -eu
cd "$(dirname "$0")/../../.."
out=.state/trials/decider; mkdir -p "$out/hf"
[ -s "$out/stage1.json" ] || podman exec -i -e CASES_JSON="$(cat scripts/trials/decider/cases.json)" substrate-voice-1 \
    python3 - < scripts/trials/decider/stage1.py > "$out/stage1.json"
podman image exists substrate-trial-decider:local || podman build -t substrate-trial-decider:local scripts/trials/decider
# pinned model revisions (Hugging Face commits, read 2026-11-22)
GLINER_REV=${GLINER_REV:-main} VELA_REV=${VELA_REV:-fa60e3aa41132c60bf05a84cabfdced39cb6d4f7}
podman run --rm --userns=keep-id ${TRIAL_NETWORK:+--network=$TRIAL_NETWORK} -e HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-0}" -e GLINER_REV="$GLINER_REV" \
    -e VELA_PATH="/home/trial/.cache/huggingface/hub/models--vllm-sr--vela3-fast/snapshots/$VELA_REV" \
    -e STAGE1=/data/stage1.json -v "$PWD/$out:/data:Z" -v "$PWD/$out/hf:/home/trial/.cache/huggingface:Z" \
    -v "$PWD/scripts/trials/decider/stage2.py:/home/trial/stage2.py:ro,Z" \
    substrate-trial-decider:local python3 -I /home/trial/stage2.py "$@" | tee -a "$out/summary.txt"
