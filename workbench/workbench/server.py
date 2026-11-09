"""The Workbench server (BRIEF.md section 7): what SQL cannot do. Behind Caddy at /wb/api/.

    GET  /wb/api/health
    GET  /wb/api/events        Server-Sent Events: what changed (Postgres NOTIFY on wb_events), as ids only
    GET  /wb/api/extractors    the extractors plugins registered
    POST /wb/api/extract       {extractor, inputs}: queue a run (pgmq queue wb_jobs); editors and owners

Every request but health carries the same JWT PostgREST checks (HS256 with WORKBENCH_JWT_SECRET, `exp`, a
wb_* `role`), verified here the same way. Events name what changed and nothing more, so a subscriber reads it
through PostgREST under its own token, and Postgres stays the one place that decides who sees what.

Settings: WORKBENCH_DATABASE_URL (the wb_server login), WORKBENCH_JWT_SECRET, WB_PLUGINS_DIR.
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import hmac
import json
import os
import time
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

from .extract import Plugins, run_extractor

ROLES = {"wb_viewer", "wb_editor", "wb_owner"}
WRITERS = {"wb_editor", "wb_owner"}
subscribers: set[asyncio.Queue] = set()
state: dict = {"plugins": None, "listening": False, "worker": False}


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def verify(token: str, secret: str, now: float | None = None) -> dict | None:
    """The claims of a valid HS256 token with an unexpired `exp` and a Workbench role; None otherwise."""
    try:
        h, p, s = token.split(".")
        if json.loads(unb64(h)).get("alg") != "HS256":
            return None
        good = hmac.new(secret.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(good, unb64(s)):
            return None
        claims = json.loads(unb64(p))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(claims.get("exp"), (int, float)) or claims["exp"] <= (now or time.time()):
        return None
    return claims if claims.get("role") in ROLES else None


def caller(request: Request) -> dict | None:
    auth = request.headers.get("authorization", "")
    return verify(auth.removeprefix("Bearer ").strip(), os.environ["WORKBENCH_JWT_SECRET"]) if auth.startswith("Bearer ") else None


def db():
    return psycopg.connect(os.environ["WORKBENCH_DATABASE_URL"])


def refused(status: int, message: str) -> JSONResponse:
    return JSONResponse({"message": message}, status_code=status)


# ------------------------------------------------------------------ routes
async def health(request: Request):
    p = state["plugins"]
    return JSONResponse({"ok": True, "listening": state["listening"], "worker": state["worker"],
                         "plugins": p.loaded if p else [], "subscribers": len(subscribers)})


async def extractors(request: Request):
    if not caller(request):
        return refused(401, "sign in first")
    return JSONResponse(state["plugins"].describe())


async def extract(request: Request):
    who = caller(request)
    if not who:
        return refused(401, "sign in first")
    if who["role"] not in WRITERS:
        return refused(403, "your role cannot run extractors")
    body = await request.json()
    key = body.get("extractor")
    if key not in state["plugins"].extractors:
        return refused(404, f"no extractor {key}")
    job = {"extractor": key, "inputs": body.get("inputs") or {}, "requested_by": who.get("name")}

    def send():
        with db() as conn:
            return conn.execute("select pgmq.send('wb_jobs', %s)", (Jsonb(job),)).fetchone()[0]
    msg = await asyncio.to_thread(send)
    return JSONResponse({"queued": msg, **job}, status_code=202)


async def events(request: Request):
    who = caller(request)
    if not who:
        return refused(401, "sign in first")
    queue: asyncio.Queue = asyncio.Queue(maxsize=500)
    subscribers.add(queue)

    async def stream():
        try:
            yield f"event: hello\ndata: {json.dumps({'name': who.get('name'), 'role': who['role']})}\n\n"
            while True:
                if time.time() >= who["exp"]:                 # the token ran out: so does the stream
                    yield "event: expired\ndata: {}\n\n"
                    return
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=20)
                    yield f"event: change\ndata: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            subscribers.discard(queue)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


# ------------------------------------------------------------------ background: NOTIFY in, jobs off the queue
async def listen():
    while True:
        try:
            async with await psycopg.AsyncConnection.connect(os.environ["WORKBENCH_DATABASE_URL"], autocommit=True) as conn:
                await conn.execute("listen wb_events")
                state["listening"] = True
                async for note in conn.notifies():
                    for q in list(subscribers):
                        with contextlib.suppress(asyncio.QueueFull):
                            q.put_nowait(note.payload)
        except (psycopg.Error, OSError):
            state["listening"] = False
            await asyncio.sleep(3)


def work_once() -> bool:
    with db() as conn:
        row = conn.execute("select msg_id, read_ct, message from pgmq.read('wb_jobs', 900, 1)").fetchone()
        conn.commit()
    if not row:
        return False
    msg_id, read_ct, job = row
    result = run_extractor(db, state["plugins"], job["extractor"], {**job.get("inputs", {}), "requested_by": job.get("requested_by")})
    if result.get("ok") or read_ct >= 3:          # done, or tried three times: archived either way, with the run recorded
        with db() as conn:
            conn.execute("select pgmq.archive('wb_jobs', %s)", (msg_id,))
    return True


async def worker():
    state["worker"] = True
    while True:
        try:
            busy = await asyncio.to_thread(work_once)
        except Exception:
            busy = False
        if not busy:
            await asyncio.sleep(2)


@contextlib.asynccontextmanager
async def lifespan(app):
    state["plugins"] = Plugins().load(Path(os.environ.get("WB_PLUGINS_DIR", "/srv/plugins")))
    tasks = [asyncio.create_task(listen()), asyncio.create_task(worker())]
    yield
    for t in tasks:
        t.cancel()


app = Starlette(routes=[
    Route("/wb/api/health", health),
    Route("/wb/api/events", events),
    Route("/wb/api/extractors", extractors),
    Route("/wb/api/extract", extract, methods=["POST"]),
], lifespan=lifespan)
