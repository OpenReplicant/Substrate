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

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
MODELS = Path(os.environ.get("VOICE_MODELS") or "/models")
GATEWAY = os.environ.get("GATEWAY_URL", "http://gateway:8080")
LLM = os.environ.get("LLM_NAME") or "local/gemma"
KEY = os.environ.get("VOICE_KEY", "")
THREADS = int(os.environ.get("VOICE_THREADS") or 4)
VOICE = os.environ.get("VOICE_STYLE") or "af_heart"
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
       "media-src 'self' blob:; frame-ancestors 'none'; object-src 'none'; base-uri 'none'")
SYSTEM = """You are the owner's companion, speaking with them out loud. Your words are turned into speech, so:
answer in one to three short spoken sentences; no lists, headings, markdown, emoji or code; say numbers the way a
person says them. Be warm, plain and direct, like a capable friend.

You cannot look things up, run anything, read files or remember beyond this conversation. A separate companion
(Claude, with tools, working in the background) can. When the owner asks for real work (finding something out,
anything with files, the web, their machine, a plan, a long answer), say briefly that you are handing it over, then
end your reply with one line of its own: HANDOFF: <the request, complete and self-contained>. Its answer will be
read out when it comes. Do not hand over small talk or what you can answer yourself.

What you hear is a speech-to-text transcript and may have small mistakes; if it makes no sense, ask once."""
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

    def vad(self):
        return self.sherpa.VoiceActivityDetector(self.vad_cfg, buffer_size_in_seconds=60)

    def transcribe(self, samples: np.ndarray) -> str:
        s = self.stt.create_stream()
        s.accept_waveform(16000, samples)
        self.stt.decode_stream(s)
        return s.result.text.strip()

    def speak(self, text: str) -> bytes:
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

    def last_reply(self) -> int:
        try:
            return self.conn().execute("select coalesce(max(id), 0) from env.action where actuator = 'companion.reply'").fetchone()[0]
        except psycopg.Error:
            self.c = None
            return 0


def chat_stream(messages: list[dict]):
    """The local model's reply, token by token (OpenAI-style streaming through the gateway)."""
    # no thinking: Gemma 4 thinks before answering by default, about 6 s to the first word here; without, 0.4 s
    body = json.dumps({"model": LLM, "messages": messages, "stream": True, "temperature": 0.7, "max_tokens": 400,
                       "reasoning_effort": os.environ.get("VOICE_REASONING") or "none"}).encode()
    req = urllib.request.Request(f"{GATEWAY}/v1/chat/completions", body,
                                 {"Content-Type": "application/json", "x-bf-vk": KEY, "x-wb-call": f"voice-{time.time_ns()}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        for line in r:
            line = line.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                return
            try:
                delta = json.loads(data)["choices"][0].get("delta") or {}
            except (ValueError, KeyError, IndexError):
                continue
            if delta.get("content"):
                yield delta["content"]


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
        self.rec.publish("companion.voice.heard", {"text": text, "audio_s": round(len(seg) / 16000, 2), "stt_ms": stt_ms}, "owner (voice)")
        self.history.append({"role": "user", "content": text})
        msgs = [{"role": "system", "content": SYSTEM}] + self.history[-20:]
        said, buf, first_ms, handoff = [], "", None, None
        q: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def pump():
            try:
                for tok in chat_stream(msgs):
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
            raise
        reply = " ".join(said)
        self.history.append({"role": "assistant", "content": reply + (f"\nHANDOFF: {handoff.strip()}" if handoff else "")})
        self.rec.publish("companion.voice.said", {"text": reply, "by": LLM, "stt_ms": stt_ms, "first_audio_ms": first_ms,
                                                  "turn_ms": round((time.perf_counter() - t0) * 1000)}, "voice head")
        if handoff and handoff.strip():
            self.rec.publish("companion.owner.message", {"text": f"(said by voice) {text}\n(the voice head's summary) {handoff.strip()}"},
                             "owner (voice, relayed by the voice head)")
            await self.send({"type": "say", "text": f"handed to the companion: {handoff.strip()}", "by": "voice head"})
        await self.state("listening")

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
        for _ in chat_stream([{"role": "system", "content": SYSTEM}, {"role": "user", "content": "Hello."}]):
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


async def companion_replies(record: Record):
    last = await asyncio.to_thread(record.last_reply)
    while True:
        await asyncio.sleep(1)
        for rid, text in await asyncio.to_thread(record.replies_after, last):
            last = rid
            for s in list(SESSIONS):
                asyncio.create_task(s.speak_companion(text or ""))


def static(path: str) -> Response | None:
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
    asyncio.create_task(warm())
    host, port = os.environ.get("VOICE_HOST", "127.0.0.1"), int(os.environ.get("VOICE_PORT") or 8110)
    async with serve(handler, host, port, process_request=process, max_size=2**20):
        log(f"on http://{host}:{port}/")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
