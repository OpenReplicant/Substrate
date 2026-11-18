"""Kokoro on the GPU while the local model generates (S-150): does speaking slow the model, and does the model
slow speaking? Run inside the voice head's container (it has Kokoro for the CPU, and reaches tts and the gateway):

    scripts/trials/voice-gpu/run.sh

Conditions, each repeated: the model alone (time to first token, tokens per second over a 300-token answer);
each voice alone (first audio of a short reply and of a sentence); each voice while the model is mid-answer (both
measured). The voices: Kokoro-FastAPI on the GPU (service tts, streamed PCM) and Kokoro on kokoro-onnx on the CPU.
One JSON line per measurement on stdout.
"""
import json
import os
import statistics
import sys
import threading
import time
import urllib.request

sys.path.insert(0, "/app")
import numpy as np  # noqa: E402

GATEWAY, KEY, MODEL = "http://gateway:8080", os.environ["VOICE_KEY"], os.environ.get("LLM_NAME", "local/gemma")
TTS = os.environ.get("TTS_URL") or "http://tts:8880"
SHORT, SENTENCE = "Sure, I can do that.", "The weather in Portland is cloudy, with rain likely after six this evening."
PROMPT = "Write one long, detailed paragraph about the history of the bicycle, from the first designs to today."


def emit(**kv):
    print(json.dumps(kv), flush=True)


def gemma(result: dict, started: threading.Event):
    body = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": PROMPT}], "stream": True,
                       "max_tokens": 300, "temperature": 0.7, "reasoning_effort": "none"}).encode()
    req = urllib.request.Request(f"{GATEWAY}/v1/chat/completions", body, {"Content-Type": "application/json", "x-bf-vk": KEY})
    t0 = time.perf_counter(); first = None; n = 0
    with urllib.request.urlopen(req, timeout=300) as r:
        for line in r:
            if not line.startswith(b"data:") or b"[DONE]" in line:
                continue
            try:
                d = (json.loads(line[5:]).get("choices") or [{}])[0].get("delta") or {}
            except ValueError:
                continue
            if d.get("content"):
                n += 1
                if first is None:
                    first = time.perf_counter() - t0
                    started.set()
    total = time.perf_counter() - t0
    result.update(first_token_s=round(first, 3), tokens=n, tokens_per_s=round((n - 1) / (total - first), 2) if n > 1 else None)


def gpu_speak(text):
    body = json.dumps({"model": "kokoro", "input": text, "voice": "af_heart", "response_format": "pcm", "stream": True}).encode()
    t0 = time.perf_counter(); first = None; size = 0
    with urllib.request.urlopen(urllib.request.Request(f"{TTS}/v1/audio/speech", body, {"Content-Type": "application/json"}), timeout=60) as r:
        while b := r.read(4096):
            first = first or time.perf_counter() - t0
            size += len(b)
    return first, time.perf_counter() - t0, size / 2 / 24000


def make_cpu():
    from kokoro_onnx import Kokoro
    os.environ.setdefault("ONNX_NUM_THREADS", os.environ.get("VOICE_THREADS", "4"))
    k = Kokoro("/models/kokoro-v1.0.int8.onnx", "/models/voices-v1.0.bin")

    def speak(text):
        t0 = time.perf_counter()
        a, sr = k.create(text, voice="af_heart", speed=1.0, lang="en-us")
        dt = time.perf_counter() - t0
        return dt, dt, len(a) / sr                   # no streaming: first audio is the whole clip
    return speak


def voice_runs(name, speak, cond, reps):
    for i in range(reps):
        for kind, text in (("short", SHORT), ("sentence", SENTENCE)):
            first, whole, audio = speak(text)
            emit(condition=cond, voice=name, kind=kind, rep=i, first_audio_s=round(first, 3), whole_s=round(whole, 3), audio_s=round(audio, 2))


def main():
    reps = int(os.environ.get("REPS") or 5)
    voices = {"gpu": gpu_speak, "cpu": make_cpu()}
    for name, sp in voices.items():                   # warm each
        sp("Hello.")
    gemma({}, threading.Event())
    for rnd in range(2):
        for i in range(3):
            res = {}
            gemma(res, threading.Event())
            emit(condition="model alone", round=rnd, rep=i, **res)
        for name, sp in voices.items():
            voice_runs(name, sp, "voice alone", reps)
        for name, sp in voices.items():
            for i in range(3):
                res, started = {}, threading.Event()
                th = threading.Thread(target=gemma, args=(res, started))
                th.start()
                started.wait(60)
                time.sleep(0.5)                       # well into the answer
                voice_runs(name, sp, "voice during model", 2)
                th.join()
                emit(condition=f"model during {name} voice", round=rnd, rep=i, **res)


if __name__ == "__main__":
    main()
