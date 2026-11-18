"""The voice head's trial (plan step 5): one candidate per process, so its peak memory is its own.

    python3 -I trial.py MODELS OUT CANDIDATE      # run.sh runs every candidate

Speech-to-text candidates (stt:*): the 73 LibriSpeech utterances (real speech, word error rate against their
transcripts, time per utterance and real-time factor), then the TTS roundtrip clips in OUT/tts/ (each TTS's
rendering of the companion sentences, word error rate against the sentence: intelligibility of that voice).
Text-to-speech candidates (tts:*): every companion sentence (time to the whole clip, real-time factor), and a
short reply's time to first audio; the clips go to OUT/tts/<candidate>/. One JSON line per case and candidate.
"""
import io
import json
import os
import resource
import re
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

THREADS = int(os.environ.get("TRIAL_THREADS") or 4)
SENTENCES = [
    "Good morning. You have two meetings today, the first one at ten.",
    "I've started a background task to look that up, and I'll tell you when it finishes.",
    "The task is done: the container runs Python three point thirteen on Debian twelve.",
    "Your daily budget is one and a half million tokens, and you've used about twelve percent of it.",
    "Do you want me to remind you about the dentist on Thursday afternoon?",
    "I couldn't reach the gateway just now, so I'll try again in a minute.",
    "Sure. Which file do you mean, the plan or the decisions log?",
    "It's twenty past four. Nothing is waiting for you.",
    "I'd propose switching to a larger model for this one, because it needs careful reasoning.",
    "Okay, I've stopped. Say my name when you want me again.",
    "The weather in Portland is cloudy, with rain likely after six this evening.",
    "That's a good question; give me a moment to think about it.",
]
SHORT = "Sure, I can do that."


ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def words(n: int) -> str:
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ("" if n % 10 == 0 else " " + ONES[n % 10])
    if n < 1000:
        return ONES[n // 100] + " hundred" + ("" if n % 100 == 0 else " " + words(n % 100))
    return str(n)


def spell(m) -> str:
    """Digits as the words a speaker says: 10 ten, 3.13 three point thirteen, 1.5 one point five, 12% twelve percent."""
    whole, _, frac = m.group(1).partition(".")
    out = words(int(whole)) + (" point " + words(int(frac)) if frac else "")
    return out + (" percent" if m.group(2) else "")


def norm(t: str) -> str:
    """Lower case, numbers spelled out (Parakeet v3 writes digits; the references are words), no punctuation."""
    t = re.sub(r"(\d+(?:\.\d+)?)(%)?", spell, t)
    t = t.lower().replace("’", "'")
    t = re.sub(r"[^a-z0-9' ]+", " ", t)
    return " ".join(t.split())


def wer(ref: str, hyp: str) -> float:
    import jiwer
    return jiwer.wer(norm(ref), norm(hyp) or "<empty>")


def emit(out, **kv):
    line = json.dumps(kv)
    print(line, flush=True)
    out.write(line + "\n")


def librispeech(models: Path):
    import pyarrow.parquet as pq
    t = pq.read_table(models / "librispeech-dummy.parquet").to_pylist()
    for r in t:
        audio, sr = sf.read(io.BytesIO(r["audio"]["bytes"]), dtype="float32")
        yield r["id"], audio, sr, r["text"]


def roundtrip(out: Path):
    for d in sorted((out / "tts").glob("*")):
        for f in sorted(d.glob("*.wav")):
            audio, sr = sf.read(f, dtype="float32")
            yield f"{d.name}/{f.stem}", audio, sr, SENTENCES[int(f.stem)]


def resample16k(audio, sr):
    if sr == 16000:
        return audio
    n = int(len(audio) * 16000 / sr)
    return np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio).astype(np.float32)


def stt(name: str, models: Path):
    if name == "stt:onnx-asr-parakeet-v3":
        import onnx_asr
        import onnxruntime as ort
        so = ort.SessionOptions()
        so.intra_op_num_threads = THREADS
        m = onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v3", models / "onnx-asr-parakeet-v3", quantization="int8", sess_options=so)
        return lambda a: m.recognize(a, sample_rate=16000)
    import sherpa_onnx
    d = next((models / {"stt:sherpa-parakeet-v3": "sherpa-parakeet-v3.d", "stt:sherpa-parakeet-110m": "sherpa-parakeet-110m.d"}[name]).iterdir())
    r = sherpa_onnx.OfflineRecognizer.from_transducer(str(d / "encoder.int8.onnx"), str(d / "decoder.int8.onnx"), str(d / "joiner.int8.onnx"),
                                                      str(d / "tokens.txt"), num_threads=THREADS, model_type="nemo_transducer")

    def rec(a):
        s = r.create_stream()
        s.accept_waveform(16000, a)
        r.decode_stream(s)
        return s.result.text
    return rec


def tts(name: str, models: Path):
    """Returns speak(text) -> (samples, sample_rate, seconds to first audio)."""
    if name == "tts:sherpa-kokoro":
        import sherpa_onnx
        d = next((models / "sherpa-kokoro.d").iterdir())
        cfg = sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(
            kokoro=sherpa_onnx.OfflineTtsKokoroModelConfig(model=str(d / "model.int8.onnx"), voices=str(d / "voices.bin"),
                                                           tokens=str(d / "tokens.txt"), data_dir=str(d / "espeak-ng-data"),
                                                           lexicon=f"{d / 'lexicon-us-en.txt'}", lang="en-us"),
            num_threads=THREADS), max_num_sentences=1)
        t = sherpa_onnx.OfflineTts(cfg)

        def speak(text):
            first = []
            t0 = time.perf_counter()

            def cb(samples, progress):
                if not first:
                    first.append(time.perf_counter() - t0)
                return 1
            a = t.generate(text, sid=3, speed=1.0, callback=cb)     # 3: af_heart in Kokoro v1.0's voice list
            return np.array(a.samples, dtype=np.float32), a.sample_rate, first[0] if first else None
        return speak
    if name == "tts:kokoro-onnx":
        from kokoro_onnx import Kokoro
        import onnxruntime as ort
        os.environ.setdefault("ONNX_NUM_THREADS", str(THREADS))
        k = Kokoro(str(models / "kokoro-onnx/kokoro-v1.0.int8.onnx"), str(models / "kokoro-onnx/voices-v1.0.bin"))

        def speak(text):
            t0 = time.perf_counter()
            a, sr = k.create(text, voice="af_heart", speed=1.0, lang="en-us")
            return a, sr, time.perf_counter() - t0                  # no streaming here: first audio is the whole clip
        return speak
    if name == "tts:kokoro-fastapi-gpu":
        import urllib.request
        url = os.environ.get("KOKORO_URL", "http://127.0.0.1:8880") + "/v1/audio/speech"

        def speak(text):
            body = json.dumps({"model": "kokoro", "input": text, "voice": "af_heart", "response_format": "pcm", "stream": True}).encode()
            t0 = time.perf_counter()
            first, chunks = None, []
            with urllib.request.urlopen(urllib.request.Request(url, body, {"Content-Type": "application/json"}), timeout=120) as r:
                while True:
                    b = r.read(4096)
                    if not b:
                        break
                    if first is None:
                        first = time.perf_counter() - t0
                    chunks.append(b)
            pcm = np.frombuffer(b"".join(chunks), dtype=np.int16).astype(np.float32) / 32768
            return pcm, 24000, first
        return speak
    if name == "tts:kokoros":
        import urllib.request
        url = os.environ.get("KOKOROS_URL", "http://127.0.0.1:3000") + "/v1/audio/speech"

        def speak(text):
            body = json.dumps({"model": "kokoro", "input": text, "voice": "af_heart", "response_format": "wav"}).encode()
            t0 = time.perf_counter()
            first, chunks = None, []
            with urllib.request.urlopen(urllib.request.Request(url, body, {"Content-Type": "application/json"}), timeout=120) as r:
                ctype = r.headers.get("Content-Type", "")
                while True:
                    b = r.read(4096)
                    if not b:
                        break
                    if first is None:
                        first = time.perf_counter() - t0
                    chunks.append(b)
            if ctype.startswith("audio/pcm"):         # Kokoros streams 16-bit mono PCM at 24 kHz whatever is asked
                return np.frombuffer(b"".join(chunks), dtype=np.int16).astype(np.float32) / 32768, 24000, first
            a, sr = sf.read(io.BytesIO(b"".join(chunks)), dtype="float32")
            return (a.mean(axis=1) if a.ndim == 2 else a), sr, first
        return speak
    raise SystemExit(f"no candidate {name}")


def main():
    models, out, name = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    res = (out / "results.jsonl").open("a")
    t0 = time.perf_counter()
    if name.startswith("stt:"):
        rec = stt(name, models)
        emit(res, candidate=name, case="load", seconds=round(time.perf_counter() - t0, 2))
        rec(np.zeros(16000, dtype=np.float32))                     # warm
        for src, cases in (("librispeech", librispeech(models)), ("roundtrip", roundtrip(out))):
            for cid, audio, sr, ref in cases:
                a = resample16k(audio, sr)
                t = time.perf_counter()
                hyp = rec(a)
                dt = time.perf_counter() - t
                emit(res, candidate=name, case=f"{src}:{cid}", audio_s=round(len(a) / 16000, 2), seconds=round(dt, 3),
                     rtf=round(dt / (len(a) / 16000), 3), wer=round(wer(ref, hyp), 3), hyp=hyp)
    else:
        speak = tts(name, models)
        emit(res, candidate=name, case="load", seconds=round(time.perf_counter() - t0, 2))
        speak("Hello.")                                            # warm
        d = out / "tts" / name.split(":", 1)[1]
        d.mkdir(parents=True, exist_ok=True)
        for i, s in enumerate(SENTENCES):
            t = time.perf_counter()
            a, sr, first = speak(s)
            dt = time.perf_counter() - t
            sf.write(d / f"{i:02d}.wav", a, sr)
            emit(res, candidate=name, case=f"sentence:{i:02d}", audio_s=round(len(a) / sr, 2), seconds=round(dt, 3),
                 rtf=round(dt / max(len(a) / sr, 1e-6), 3), first_audio_s=round(first, 3) if first else None)
        for i in range(3):
            a, sr, first = speak(SHORT)
            emit(res, candidate=name, case=f"short:{i}", audio_s=round(len(a) / sr, 2), first_audio_s=round(first, 3) if first else None)
    emit(res, candidate=name, case="peak_rss_mb", value=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024)


if __name__ == "__main__":
    main()
