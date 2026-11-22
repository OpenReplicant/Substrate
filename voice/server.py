"""The voice head (plan step 5, S-147): talk to the companion out loud, with a face.

    python3 -m voice.server        # compose service `voice`, on 127.0.0.1:VOICE_PORT (8110)

The page (voice/static) sends the microphone as 16 kHz mono 16-bit PCM over a WebSocket. Here, Silero (sherpa-onnx)
cuts it into utterances; Parakeet TDT 110M turns each into text; the local model (LLM_NAME, through the gateway
under the caller key voice:head) answers it, streamed; each sentence is spoken by Kokoro (kokoro-onnx) and sent back
as 24 kHz 16-bit PCM, which the page plays and moves the face's mouth to. Speaking over it stops it (barge-in).

Real work is the companion's: when the model ends a reply with a line `HANDOFF: <the request>`, the request is
published as companion.owner.message, as the owner's (relayed by voice), and the companion's replies (applied
companion.reply actions) are spoken here too. Everything heard and said is in the record (companion.voice.heard,
companion.voice.said); the voice stream itself is not subscribed by the companion's session, so only handed-off
requests reach Anthropic (S-136's loosening covers the owner's messages to the companion).

Messages to the page (JSON text frames): {"type": "state", "state": listening|hearing|thinking|speaking},
{"type": "heard", "text"}, {"type": "say", "text", "by"}, {"type": "audio", "rate": 24000} before each binary
frame of audio, {"type": "stop"} to drop queued audio, {"type": "error", "text"}.
"""
from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import psycopg
from psycopg.types.json import Jsonb
from websockets.asyncio.server import serve
from websockets.datastructures import Headers
from websockets.http11 import Response

from voice import reply, route

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
MODELS = Path(os.environ.get("VOICE_MODELS") or "/models")
GATEWAY = os.environ.get("GATEWAY_URL", "http://gateway:8080")
LLM = os.environ.get("LLM_NAME") or "local/slow"
KEY = os.environ.get("VOICE_KEY", "")
# the router (S-170): tools (the default): LLM calls talk, delegate or save_note each turn; embed: an embedding vote
# decides talk or work first; off: LLM's reply component decides with its HANDOFF line (to the companion), as before
ROUTER = (os.environ.get("VOICE_ROUTER") or "tools").strip()
NOTED = "Noted."
EMBED_MODEL = os.environ.get("EMBED_MODEL") or "ollama/qwen3-embedding:0.6b"
ON_IT = "On it. I'll tell you when it's done."
WORKER_SAYS = ("Say this result to the owner out loud in one to three short spoken sentences: plain words, no lists, "
               "markdown, file paths read character by character, or code. Keep what matters; drop the rest.")
THREADS = int(os.environ.get("VOICE_THREADS") or 4)
VOICE = os.environ.get("VOICE_STYLE") or "af_heart"
TTS_URL = os.environ.get("TTS_URL", "").rstrip("/")
AVATAR_DIR = Path(os.environ.get("AVATAR_DIR") or "/avatar")
AVATAR_FILE = (os.environ.get("AVATAR_FILE") or "").strip()
AVATAR_TYPES = {".gltf": "model/gltf+json", ".glb": "model/gltf-binary", ".vrm": "model/gltf-binary", ".bin": "application/octet-stream",
                ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".ktx2": "image/ktx2"}
CSP = ("default-src 'self'; script-src 'self' 'sha256-IMPORTMAP'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self' blob:; "
       "media-src 'self' blob:; frame-ancestors 'none'; object-src 'none'; base-uri 'none'")

def importmap_hash() -> str:
    """The page's one inline script, the import map, is allowed by its hash; everything else stays 'self'."""
    import base64, hashlib
    m = re.search(r"<script type=\"importmap\">(.*?)</script>", (STATIC / "index.html").read_text(encoding="utf-8"), re.S)
    return base64.b64encode(hashlib.sha256(m.group(1).encode()).digest()).decode() if m else ""


CSP = CSP.replace("sha256-IMPORTMAP", "sha256-" + importmap_hash())


def avatar_url() -> str:
    """AVATAR_FILE is a repo path such as .state/avatar/x/scene.gltf; the folder is mounted at /avatar. '' when unset or missing."""
    if not AVATAR_FILE:
        return ""
    rel = AVATAR_FILE.split(".state/avatar/", 1)[1] if ".state/avatar/" in AVATAR_FILE else Path(AVATAR_FILE).name
    return "/avatar/" + rel if avatar_file("/avatar/" + rel) else ""


def avatar_file(path: str) -> Path | None:
    """A file under AVATAR_DIR only: resolved, so no .. or symlink gets out; and only the types a model needs."""
    from urllib.parse import unquote
    root = AVATAR_DIR.resolve()
    f = (root / unquote(path.removeprefix("/avatar/"))).resolve()
    return f if root in f.parents and f.is_file() and f.suffix.lower() in AVATAR_TYPES else None


def avatar_response(path: str) -> Response:
    f = avatar_file(path)
    if not f:
        return Response(404, "Not Found", Headers({"Content-Type": "text/plain"}), b"not found")
    return Response(200, "OK", Headers({"Content-Type": AVATAR_TYPES[f.suffix.lower()], "Cache-Control": "no-store",
                                        "X-Content-Type-Options": "nosniff"}), f.read_bytes())


SENTENCE = re.compile(r"(.+?[.!?…])\s+", re.S)     # a sentence ends at its mark and the space after it (not "3.13")


def sentences(text: str) -> list[str]:
    out, rest = [], text.strip() + " "
    while m := SENTENCE.match(rest):
        out.append(m.group(1).strip())
        rest = rest[m.end():]
    return out + ([rest.strip()] if rest.strip() else [])


def log(*a):
    print("voice:", *a, file=sys.stderr, flush=True)


class Models:
    """The speech models, loaded once; each call runs in a worker thread."""

    def __init__(self):
        import sherpa_onnx
        from kokoro_onnx import Kokoro
        d = MODELS / "parakeet-110m"
        d = next(d.iterdir()) if not (d / "tokens.txt").exists() else d
        self.stt = sherpa_onnx.OfflineRecognizer.from_transducer(
            str(d / "encoder.int8.onnx"), str(d / "decoder.int8.onnx"), str(d / "joiner.int8.onnx"), str(d / "tokens.txt"),
            num_threads=THREADS, model_type="nemo_transducer")
        cfg = sherpa_onnx.VadModelConfig()
        cfg.silero_vad.model = str(MODELS / "silero_vad.onnx")
        cfg.silero_vad.threshold = float(os.environ.get("VOICE_VAD_THRESHOLD") or 0.5)
        cfg.silero_vad.min_silence_duration = float(os.environ.get("VOICE_SILENCE_S") or 0.6)
        cfg.silero_vad.min_speech_duration = 0.25
        cfg.silero_vad.max_speech_duration = 30
        cfg.sample_rate = 16000
        cfg.num_threads = 1
        self.vad_cfg, self.sherpa = cfg, sherpa_onnx
        os.environ.setdefault("ONNX_NUM_THREADS", str(THREADS))
        self.tts = Kokoro(str(MODELS / "kokoro-v1.0.int8.onnx"), str(MODELS / "voices-v1.0.bin"))
        self.tts_down_until = 0.0

    def vad(self):
        return self.sherpa.VoiceActivityDetector(self.vad_cfg, buffer_size_in_seconds=60)

    def transcribe(self, samples: np.ndarray) -> str:
        s = self.stt.create_stream()
        s.accept_waveform(16000, samples)
        self.stt.decode_stream(s)
        return s.result.text.strip()

    def speak(self, text: str) -> bytes:
        """24 kHz 16-bit mono PCM: from Kokoro on the GPU (TTS_URL, S-150) when it answers, else Kokoro here on the CPU."""
        if TTS_URL and time.monotonic() >= self.tts_down_until:
            try:
                body = json.dumps({"model": "kokoro", "input": text, "voice": VOICE, "response_format": "pcm", "stream": False}).encode()
                req = urllib.request.Request(f"{TTS_URL}/v1/audio/speech", body, {"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=20) as r:
                    return r.read()
            except (OSError, ValueError) as e:
                log(f"Kokoro on the GPU did not answer ({e}); on the CPU for a minute")
                self.tts_down_until = time.monotonic() + 60
        a, _ = self.tts.create(text, voice=VOICE, speed=1.0, lang="en-us")
        return (np.clip(a, -1, 1) * 32767).astype(np.int16).tobytes()


class Record:
    """The environment's record: what was heard and said, handoffs, and the companion's replies to speak."""

    def __init__(self):
        self.c = None

    def conn(self):
        if self.c is None or self.c.closed:
            self.c = psycopg.connect(os.environ["STORE_URL"], autocommit=True)
        return self.c

    def publish(self, key: str, body: dict, source: str) -> int | None:
        try:
            return self.conn().execute("select env.publish(%s, %s, %s)", (key, Jsonb(body), source)).fetchone()[0]
        except psycopg.Error as e:
            log(f"record: {e}")
            self.c = None
            return None

    def replies_after(self, last: int) -> list[tuple[int, str]]:
        try:
            return self.conn().execute("select id, input->>'text' from env.action where actuator = 'companion.reply' "
                                       "and status = 'applied' and id > %s order by id", (last,)).fetchall()
        except psycopg.Error as e:
            log(f"record: {e}")
            self.c = None
            return []

    def reply_component(self) -> tuple[int | None, dict]:
        """The active version of the reply component (S-151), read again at most every 10 s; the seed if none."""
        now = time.monotonic()
        if now - getattr(self, "_card_at", -1e9) > 10:
            try:
                row = self.conn().execute("select id, card from env.active_component('companion', %s)", (reply.NAME,)).fetchone()
                self._card = (row[0], row[1]) if row else (None, reply.SEED)
            except psycopg.Error as e:
                log(f"record: {e}")
                self.c = None
                self._card = getattr(self, "_card", (None, reply.SEED))
            self._card_at = now
        return self._card

    def route_examples(self) -> tuple[int, list[tuple[str, str]]]:
        """The owner's corrections (voice.route.example signals) after the seed: (the last one's id, the examples)."""
        try:
            rows = self.conn().execute("select id, body->>'text', body->>'route' from env.signal where key = 'voice.route.example' "
                                       "order by id").fetchall()
            return (rows[-1][0] if rows else 0), [(t, r) for _, t, r in rows if t and r in route.ROUTES]
        except psycopg.Error as e:
            log(f"record: {e}")
            self.c = None
            return -1, []

    def worker_done_after(self, last: int) -> list[tuple[int, str, bool]]:
        """The worker's finished tasks that the voice head asked for: reply_to voice, or voice:quiet when it failed
        (a saved note is confirmed at once with "Noted"; only a failure is read out)."""
        try:
            return self.conn().execute("select id, body->>'text', coalesce((body->>'ok')::boolean, false) from env.signal "
                                       "where key = 'worker.task.done' and id > %s and (body->>'reply_to' = 'voice' or "
                                       "(body->>'reply_to' = 'voice:quiet' and not coalesce((body->>'ok')::boolean, false))) "
                                       "order by id", (last,)).fetchall()
        except psycopg.Error as e:
            log(f"record: {e}")
            self.c = None
            return []

    def last_worker_done(self) -> int:
        try:
            return self.conn().execute("select coalesce(max(id), 0) from env.signal where key = 'worker.task.done'").fetchone()[0]
        except psycopg.Error:
            self.c = None
            return 0

    def last_reply(self) -> int:
        try:
            return self.conn().execute("select coalesce(max(id), 0) from env.action where actuator = 'companion.reply'").fetchone()[0]
        except psycopg.Error:
            self.c = None
            return 0


class Session:
    """One page's conversation: its microphone, its turns, its playback."""

    def __init__(self, ws, models: Models, record: Record):
        self.ws, self.m, self.rec = ws, models, record
        self.vad = models.vad()
        self.history: list[dict] = []
        self.turn: asyncio.Task | None = None
        self.speaking_until = 0.0
        self.hearing = False
        self.out = asyncio.Lock()

    async def send(self, obj: dict, audio: bytes | None = None):
        async with self.out:
            await self.ws.send(json.dumps(obj))
            if audio is not None:
                await self.ws.send(audio)

    async def state(self, s: str):
        await self.send({"type": "state", "state": s})

    async def interrupt(self):
        if self.turn and not self.turn.done():
            self.turn.cancel()
        await self.send({"type": "stop"})

    async def audio_in(self, frame: bytes):
        samples = np.frombuffer(frame, dtype=np.int16).astype(np.float32) / 32768
        self.vad.accept_waveform(samples)
        if self.vad.is_speech_detected() and not self.hearing:
            self.hearing = True
            await self.interrupt()                      # barge-in: the owner speaking stops the reply
            await self.state("hearing")
        while not self.vad.empty():
            seg = np.array(self.vad.front.samples, dtype=np.float32)
            self.vad.pop()
            self.hearing = False
            self.turn = asyncio.create_task(self.respond(seg))

    async def respond(self, seg: np.ndarray):
        t0 = time.perf_counter()
        await self.state("thinking")
        text = await asyncio.to_thread(self.m.transcribe, seg)
        stt_ms = round((time.perf_counter() - t0) * 1000)
        if not text:
            return await self.state("listening")
        await self.send({"type": "heard", "text": text})
        heard = self.rec.publish("companion.voice.heard", {"text": text, "audio_s": round(len(seg) / 16000, 2), "stt_ms": stt_ms}, "owner (voice)")
        if ROUTER == "tools":
            return await self.tools_turn(text, heard, stt_ms, t0)
        decided, why = await asyncio.to_thread(ROUTE.decide, text)
        if decided == "work":
            return await self.hand_to_worker(text, heard, stt_ms, why, t0)
        comp_id, card = await asyncio.to_thread(self.rec.reply_component)
        prior = list(self.history)
        self.history.append({"role": "user", "content": text})
        said, buf, first_ms, handoff = [], "", None, None
        q: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def pump():
            try:
                for tok in reply.stream(card, prior, text, GATEWAY, KEY, LLM):
                    loop.call_soon_threadsafe(q.put_nowait, tok)
            except Exception as e:                      # noqa: BLE001 - reported to the page, and the turn ends
                loop.call_soon_threadsafe(q.put_nowait, e)
            loop.call_soon_threadsafe(q.put_nowait, None)
        worker = loop.run_in_executor(None, pump)
        try:
            while True:
                tok = await q.get()
                if isinstance(tok, Exception):
                    await self.send({"type": "error", "text": f"the local model: {tok}"})
                    break
                if tok is not None:
                    buf += tok
                if "HANDOFF:" in buf:
                    pre, _, rest = buf.partition("HANDOFF:")
                    if pre.strip():
                        await self.say(pre.strip(), said)
                    buf, handoff = "", rest
                    if tok is None:
                        break
                    continue
                if handoff is not None:
                    handoff += tok or ""
                    if tok is None:
                        break
                    continue
                while m := SENTENCE.match(buf):
                    sentence, buf = m.group(1).strip(), buf[m.end():]
                    if first_ms is None:
                        first_ms = round((time.perf_counter() - t0) * 1000)
                    await self.say(sentence, said)
                if tok is None:
                    if buf.strip():
                        await self.say(buf.strip(), said)
                    break
        except asyncio.CancelledError:
            self.history.append({"role": "assistant", "content": " ".join(said) + " (interrupted)"})
            self.rec.publish("companion.voice.said", {"text": " ".join(said), "by": LLM, "heard": heard, "component": comp_id,
                                                      "interrupted": True, "stt_ms": stt_ms, "first_audio_ms": first_ms}, "voice head")
            raise
        spoken = " ".join(said)
        dropped = None
        if decided == "talk" and handoff is not None:                # the router said talk: the model's hand-over is not sent
            dropped, handoff = (handoff.strip() or None), None
        self.history.append({"role": "assistant", "content": spoken + (f"\nHANDOFF: {handoff.strip()}" if handoff else "")})
        self.rec.publish("companion.voice.said", {"text": spoken, "by": LLM, "heard": heard, "component": comp_id,
                                                  "route": decided, "routed_by": why, "handoff_dropped": dropped,
                                                  "handoff": (handoff or "").strip() or None, "stt_ms": stt_ms,
                                                  "first_audio_ms": first_ms, "turn_ms": round((time.perf_counter() - t0) * 1000)},
                         "voice head")
        if handoff and handoff.strip():
            self.rec.publish("companion.owner.message", {"text": f"(said by voice) {text}\n(the voice head's summary) {handoff.strip()}"},
                             "owner (voice, relayed by the voice head)")
            await self.send({"type": "say", "text": f"handed to the companion: {handoff.strip()}", "by": "voice head"})
        await self.state("listening")

    async def tools_turn(self, text: str, heard, stt_ms: int, t0: float):
        """One turn decided by the tool the voice model calls (S-170): talk is spoken; delegate goes to the worker with
        "on it"; save_note goes to the worker as the example plan's "save a note called ..." (no model call there)."""
        body = json.dumps(route.tools_body(LLM, self.history[-20:], text)).encode()
        req = urllib.request.Request(f"{GATEWAY}/v1/chat/completions", body, {"Content-Type": "application/json", "x-bf-vk": KEY,
                                                                              "x-wb-call": f"voice-{time.time_ns()}"})
        try:
            msg = (await asyncio.to_thread(lambda: json.load(urllib.request.urlopen(req, timeout=60))))["choices"][0]["message"]
            tool, arg = route.tools_decision(msg)
        except Exception as e:                                       # noqa: BLE001 - reported, and the turn ends
            await self.send({"type": "error", "text": f"the voice model: {e}"})
            return await self.state("listening")
        decide_ms = round((time.perf_counter() - t0) * 1000)
        said: list = []
        self.history.append({"role": "user", "content": text})
        if tool == "talk":
            for sentence in sentences(arg) or [arg]:
                await self.say(sentence, said)
        elif tool == "delegate":
            self.rec.publish("worker.owner.message", {"text": arg, "said": text, "reply_to": "voice"}, "owner (voice)")
            await self.say(ON_IT, said)
        elif tool == "save_note":
            self.rec.publish("worker.owner.message", {"text": f"save a note called {route.note_name(arg)}: {arg}",
                                                      "said": text, "reply_to": "voice:quiet"}, "owner (voice)")
            await self.say(NOTED, said)
        else:
            await self.say("Sorry, could you say that again?", said)
        spoken = " ".join(said)
        self.history.append({"role": "assistant", "content": spoken + ({"delegate": " (handed to the worker)",
                                                                       "save_note": " (saved as a note)"}.get(tool, ""))})
        self.rec.publish("companion.voice.said", {"text": spoken, "by": LLM, "heard": heard, "route": tool or None, "routed_by": "tools",
                                                  "tool_text": arg if tool != "talk" else None, "stt_ms": stt_ms, "decide_ms": decide_ms,
                                                  "turn_ms": round((time.perf_counter() - t0) * 1000)}, "voice head")
        await self.state("listening")

    async def hand_to_worker(self, text: str, heard, stt_ms: int, why: dict, t0: float):
        """Work: say so at once, and put the request on the worker's queue; its answer is read out when it comes."""
        said: list = []
        self.rec.publish("worker.owner.message", {"text": text, "reply_to": "voice"}, "owner (voice)")
        await self.say(ON_IT, said)
        first_ms = round((time.perf_counter() - t0) * 1000)
        self.history.append({"role": "user", "content": text})
        self.history.append({"role": "assistant", "content": ON_IT + " (handed to the worker)"})
        self.rec.publish("companion.voice.said", {"text": ON_IT, "by": "voice head", "heard": heard, "route": "work",
                                                  "routed_by": why, "to": "worker", "stt_ms": stt_ms, "first_audio_ms": first_ms},
                         "voice head")
        await self.state("listening")

    async def speak_worker(self, text: str, ok: bool):
        """The worker's answer, condensed by the voice model into a few spoken sentences and read out in a quiet moment."""
        while self.hearing or (self.turn and not self.turn.done()):
            await asyncio.sleep(0.3)
        card = {"params": {"system": WORKER_SAYS, "temperature": 0.3, "max_tokens": 200, "reasoning_effort": "none",
                           "history_turns": 0}}
        try:
            spoken = "".join(await asyncio.to_thread(lambda: list(reply.stream(card, [], text, GATEWAY, KEY, LLM)))).strip()
            spoken = reply.split(spoken)[0] or spoken
        except Exception as e:                                       # noqa: BLE001 - the answer is read as it is
            log(f"condensing the worker's answer: {e}")
            spoken = " ".join(sentences(text)[:3])
        spoken = re.sub(r"[`*_#]+", "", spoken).strip()               # markdown the model kept would be read out
        if not ok:
            spoken = "The task did not finish. " + spoken
        self.history.append({"role": "assistant", "content": f"(the worker's answer) {spoken}"})
        await self.send({"type": "say", "text": spoken, "by": "worker"})
        for sentence in sentences(spoken) or [spoken]:
            pcm = await asyncio.to_thread(self.m.speak, sentence)
            await self.send({"type": "audio", "rate": 24000}, pcm)
        self.rec.publish("companion.voice.said", {"text": spoken, "by": "worker", "condensed_from": text[:2000]}, "voice head")

    async def say(self, sentence: str, said: list):
        said.append(sentence)
        await self.state("speaking")
        pcm = await asyncio.to_thread(self.m.speak, sentence)
        await self.send({"type": "say", "text": sentence, "by": LLM})
        await self.send({"type": "audio", "rate": 24000}, pcm)

    async def speak_companion(self, text: str):
        """The companion's reply, read out (it arrives in the background, so it waits for a quiet moment)."""
        while self.hearing or (self.turn and not self.turn.done()):
            await asyncio.sleep(0.3)
        await self.send({"type": "say", "text": text, "by": "companion"})
        for sentence in sentences(text):
            pcm = await asyncio.to_thread(self.m.speak, sentence)
            await self.send({"type": "audio", "rate": 24000}, pcm)
        self.rec.publish("companion.voice.said", {"text": text, "by": "companion"}, "voice head")


SESSIONS: set[Session] = set()


async def warm():
    """Read the voice prompt into the model once, so the owner's first sentence finds it cached: just after the
    model loads, reading those 243 tokens took 14 s (the weights paged in from disk); cached, 0.55 s."""
    def once():
        _, card = Record().reply_component()
        for _ in reply.stream(card, [], "Hello.", GATEWAY, KEY, LLM):
            pass
    while True:
        try:
            t = time.perf_counter()
            await asyncio.to_thread(once)
            log(f"the local model is warm ({time.perf_counter() - t:.1f} s)")
            return
        except Exception as e:                          # noqa: BLE001 - the model may still be loading
            log(f"warming the local model: {e}; again in 15 s")
            await asyncio.sleep(15)


class Route:
    """The router as the voice head runs it: built once its embeddings answer, rebuilt when the owner adds an example.
    decide() returns (None, {}) when routing is off or not ready, and the model's own HANDOFF line decides, as before."""

    def __init__(self):
        self.router, self.seen = None, None

    def embed(self, texts: list[str]) -> list[list[float]]:
        body = json.dumps({"model": EMBED_MODEL, "input": texts}).encode()
        req = urllib.request.Request(f"{GATEWAY}/v1/embeddings", body, {"Content-Type": "application/json", "x-bf-vk": KEY})
        with urllib.request.urlopen(req, timeout=30) as r:
            return [d["embedding"] for d in sorted(json.load(r)["data"], key=lambda d: d["index"])]

    def refresh(self, record: Record) -> None:
        last, extra = record.route_examples()
        if last < 0 or (self.router is not None and last == self.seen):
            return
        self.router = route.Router(self.embed, route.SEED + extra)
        self.seen = last
        log(f"router: {len(route.SEED)} seed and {len(extra)} owner examples")

    def decide(self, text: str) -> tuple[str | None, dict]:
        if ROUTER != "embed" or self.router is None:
            return None, {}
        try:
            t = time.perf_counter()
            r, why = self.router.route(text)
            return r, {**why, "ms": round((time.perf_counter() - t) * 1000)}
        except Exception as e:                                       # noqa: BLE001 - the model decides, as before
            log(f"router: {e}")
            return None, {"error": str(e)[:200]}


ROUTE = Route()


async def keep_router(record: Record):
    while ROUTER == "embed":
        try:
            await asyncio.to_thread(ROUTE.refresh, record)
        except Exception as e:                                       # noqa: BLE001 - e.g. the embedding model not up yet
            log(f"router not ready: {e}")
        await asyncio.sleep(30 if ROUTE.router else 5)


async def worker_replies(record: Record):
    last = await asyncio.to_thread(record.last_worker_done)
    while True:
        await asyncio.sleep(1)
        for sid, text, ok in await asyncio.to_thread(record.worker_done_after, last):
            last = sid
            for s in list(SESSIONS):
                asyncio.create_task(s.speak_worker(text or "", ok))


async def companion_replies(record: Record):
    last = await asyncio.to_thread(record.last_reply)
    while True:
        await asyncio.sleep(1)
        for rid, text in await asyncio.to_thread(record.replies_after, last):
            last = rid
            for s in list(SESSIONS):
                asyncio.create_task(s.speak_companion(text or ""))


def static(path: str) -> Response | None:
    if path.startswith("/avatar/"):
        return avatar_response(path)
    if path == "/config.json":
        return Response(200, "OK", Headers({"Content-Type": "application/json", "Cache-Control": "no-store"}),
                        json.dumps({"avatar": avatar_url()}).encode())
    rel = "index.html" if path in ("/", "/index.html") else path.removeprefix("/static/") if path.startswith("/static/") else None
    f = (STATIC / rel).resolve() if rel else None
    if not f or not f.is_file() or STATIC.resolve() not in f.parents:
        return Response(404, "Not Found", Headers({"Content-Type": "text/plain"}), b"not found")
    ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
    if ctype.startswith("text/") or ctype.endswith("javascript"):
        ctype += "; charset=utf-8"
    return Response(200, "OK", Headers({"Content-Type": ctype, "Content-Security-Policy": CSP, "Cache-Control": "no-store",
                                        "X-Content-Type-Options": "nosniff"}), f.read_bytes())


async def main():
    models, record = await asyncio.to_thread(Models), Record()
    log("models loaded")

    async def handler(ws):
        host = ws.request.headers.get("Host", "")
        if ws.request.headers.get("Origin") not in (f"http://{host}", f"https://{host}"):
            return await ws.close(1008, "only from this page")
        s = Session(ws, models, record)
        SESSIONS.add(s)
        await s.state("listening")
        try:
            async for msg in ws:
                if isinstance(msg, bytes):
                    await s.audio_in(msg)
                elif json.loads(msg).get("type") == "stop":
                    await s.interrupt()
        finally:
            SESSIONS.discard(s)
            if s.turn:
                s.turn.cancel()

    def process(conn, request):
        if request.headers.get("Upgrade", "").lower() != "websocket":
            return static(request.path.split("?", 1)[0])
        return None

    asyncio.create_task(companion_replies(record))
    asyncio.create_task(worker_replies(record))
    asyncio.create_task(keep_router(record))
    asyncio.create_task(warm())
    host, port = os.environ.get("VOICE_HOST", "127.0.0.1"), int(os.environ.get("VOICE_PORT") or 8110)
    async with serve(handler, host, port, process_request=process, max_size=2**20):
        log(f"on http://{host}:{port}/")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
