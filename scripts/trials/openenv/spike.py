"""The OpenEnv spike (S-184, plan step 1): openenv 0.12.0, one Postgres-backed environment, the seven points.

    python3 -I spike.py all | p1 | p2 | p3 | p47      (in the trial image; scripts/trials/openenv/run.sh)

Each point prints one JSON result line; run.sh keeps them in .state/trials/openenv/results.jsonl.
Trial only: throwaway databases openenv_trial* on the stack's Postgres, dropped at the end.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from typing import Any, AsyncIterator, Optional

import psycopg
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastmcp import FastMCP

from openenv.core.env_server.http_server import create_app
from openenv.core.env_server.interfaces import Environment  # noqa: F401  (the base the classes below extend)
from openenv.core.env_server.mcp_environment import MCPEnvironment
from openenv.core.env_server.mcp_types import CallToolAction, CallToolObservation
from openenv.core.env_server.types import Observation, State
from openenv.core.harness import (AgenticHarnessAdapter, HarnessAction, HarnessConfig, HarnessEnvironment,
                                  HarnessEvent, HarnessEventType)
from openenv.core.mcp_client import MCPToolClient
from openenv.core.rubrics import Rubric

LIVE, TMPL = "openenv_trial", "openenv_trial_tmpl"
HOST = os.environ.get("PGHOST", "db")


def dsn(db: str = "postgres") -> str:
    return f"postgresql://postgres:{os.environ['POSTGRES_PASSWORD']}@{HOST}:5432/{db}"


def sql(db: str, q: str, args: tuple = (), fetch: bool = False):
    with psycopg.connect(dsn(db), autocommit=True) as c:
        cur = c.execute(q, args)
        return cur.fetchall() if fetch else None


def result(point: int, ok: bool, line: str, **data):
    print(json.dumps({"point": point, "ok": ok, "result": line, **data}), flush=True)


SCHEMA = """
create table if not exists note (id bigserial primary key, session text, episode text, body text,
                                 at timestamptz default clock_timestamp());
create table if not exists proposal (id bigserial primary key, session text, action text, status text default 'waiting');
create table if not exists model_call (id bigserial primary key, episode text, path text, kind text,
                                       has_tools bool, at timestamptz default clock_timestamp());
create table if not exists outcome (episode text primary key, score float, at timestamptz default clock_timestamp());
create or replace function note_event() returns trigger language plpgsql as $$
begin perform pg_notify('note', json_build_object('id', new.id, 'session', new.session, 'body', new.body,
                                                  'at', extract(epoch from new.at))::text); return new; end $$;
drop trigger if exists note_event on note;
create trigger note_event after insert on note for each row execute function note_event();
"""


def setup():
    for db in (LIVE, TMPL):
        if not sql("postgres", "select 1 from pg_database where datname=%s", (db,), fetch=True):
            sql("postgres", f'create database "{db}"')
        sql(db, SCHEMA)
    # the template carries some data, so the clone copies something (10k notes, ~1 MB)
    if sql(TMPL, "select count(*) from note", fetch=True)[0][0] == 0:
        sql(TMPL, "insert into note(session, body) select 'seed', md5(g::text) from generate_series(1, 10000) g")
    sql("postgres", f'alter database "{TMPL}" with is_template true')


def teardown():
    rows = sql("postgres", "select datname from pg_database where datname like 'openenv_ep_%%'", fetch=True)
    for (db,) in rows:
        sql("postgres", f'drop database "{db}" with (force)')


# ---- the environment: state in Postgres, so every session is a view of one live environment -------------------

class NotesEnv(MCPEnvironment):
    """Tools over Postgres. Production: every session reads and writes the live database. Simulation: reset()
    clones the template database and the episode works on its copy."""
    SUPPORTS_CONCURRENT_SESSIONS = True

    def __init__(self, db: str = LIVE):
        mcp = FastMCP("notes")
        self.db, self.session = db, uuid.uuid4().hex[:8]
        self._state = State(episode_id=None, step_count=0)
        env = self

        @mcp.tool
        def note_add(body: str) -> str:
            """Add a note to the shared notebook."""
            (nid,), = sql(env.db, "insert into note(session, episode, body) values (%s, %s, %s) returning id",
                          (env.session, env._state.episode_id, body), fetch=True)
            return f"noted #{nid}"

        @mcp.tool
        def notes_list(limit: int = 20) -> list[str]:
            """The newest notes, from every session."""
            return [f"{s}: {b}" for s, b in sql(env.db, "select session, body from note where session <> 'seed' "
                                                "order by id desc limit %s", (limit,), fetch=True)]

        @mcp.tool
        def propose(action: str) -> dict:
            """Ask the owner to approve an action; returns at once with the proposal's id (the gate, S-143)."""
            (pid,), = sql(env.db, "insert into proposal(session, action) values (%s, %s) returning id",
                          (env.session, action), fetch=True)
            return {"status": "waiting_for_approval", "proposal_id": pid}

        super().__init__(mcp)

    def reset(self, seed=None, episode_id=None, **kw) -> Observation:
        ep = episode_id or uuid.uuid4().hex
        name = f"openenv_ep_{ep[:12]}"
        t0 = time.perf_counter()
        sql("postgres", f'create database "{name}" template "{TMPL}" strategy {kw.get("strategy", "file_copy")}')
        ms = (time.perf_counter() - t0) * 1000
        self.db, self._state = name, State(episode_id=ep, step_count=0)
        return Observation(done=False, reward=0.0, metadata={"episode_id": ep, "db": name, "clone_ms": ms})

    def _step_impl(self, action, timeout_s=None, **kw) -> Observation:
        return Observation(done=False, reward=0.0, metadata={"error": "only MCP tool calls"})

    @property
    def state(self) -> State:
        return self._state


def serve(app, port: int) -> uvicorn.Server:
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=srv.run, daemon=True).start()
    while not srv.started:
        time.sleep(0.05)
    return srv


# ---- points 1 and 2: many sessions on one live environment, events to a subscriber ---------------------------

async def p1_p2():
    app = create_app(NotesEnv, CallToolAction, CallToolObservation, max_concurrent_envs=8, mode="production")
    routes = sorted({getattr(r, "path", "") for r in app.routes})
    srv = serve(app, 8765)
    got: list[tuple[float, dict]] = []
    ready = threading.Event()

    def listen():
        with psycopg.connect(dsn(LIVE), autocommit=True) as c:
            c.execute("listen note")
            ready.set()
            for n in c.notifies(timeout=20, stop_after=6):
                got.append((time.time(), json.loads(n.payload)))
    t = threading.Thread(target=listen, daemon=True)
    t.start()
    ready.wait(5)
    sql(LIVE, "truncate note, proposal")
    try:
        clients = [MCPToolClient("http://127.0.0.1:8765", mode="production") for _ in range(3)]
        for c in clients:
            await c.connect()
        for i, c in enumerate(clients):
            await c.call_tool("note_add", body=f"from agent {i}")
            await c.call_tool("note_add", body=f"again from agent {i}")
        seen = [await c.call_tool("notes_list") for c in clients]
        gate = await clients[0].call_tool("propose", action="send the weekly email")
        for c in clients:
            await c.close()
    finally:
        srv.should_exit = True
    t.join(25)
    def as_list(x):
        x = getattr(x, "data", None) or getattr(x, "structured_content", None) or x
        if isinstance(x, dict) and "result" in x:
            x = x["result"]
        return x if isinstance(x, list) else [str(x)]
    lists = [as_list(s) for s in seen]
    sessions = {r[0] for r in sql(LIVE, "select distinct session from note", fetch=True)}
    shared = all(len(l) == 6 for l in lists) and len(sessions) == 3
    result(1, shared, f"3 MCP sessions on one production server ({len(sessions)} server-side env instances) each "
           f"saw all {len(lists[0])} notes written by all three: state lives in Postgres, not the instance; "
           f"OpenEnv's production routes: {[r for r in routes if r]}",
           seen=lists, propose=str(getattr(gate, 'data', gate)))
    lat = [(ts - p["at"]) * 1000 for ts, p in got]
    result(2, len(got) == 6, f"{len(got)}/6 inserts reached a LISTEN subscriber, median "
           f"{statistics.median(lat):.1f} ms after commit (a trigger's pg_notify); OpenEnv itself pushes nothing "
           f"in production mode (request/response only), so events come from Postgres (NOTIFY here, pgmq as "
           f"environment/ does)" if got else "no events arrived",
           latency_ms=[round(x, 2) for x in lat])


# ---- point 3: reset clones a template database -------------------------------------------------------------

def p3():
    env = NotesEnv()
    out = {}
    for strategy in ("file_copy", "wal_log"):
        ms = [env.reset(strategy=strategy).metadata["clone_ms"] for _ in range(10)]
        out[strategy] = {"median_ms": round(statistics.median(ms), 1), "max_ms": round(max(ms), 1)}
    env.reset()
    n = sql(env.db, "select count(*) from note", fetch=True)[0][0]
    size = sql("postgres", "select pg_size_pretty(pg_database_size(%s))", (TMPL,), fetch=True)[0][0]
    teardown()
    best = min(v["median_ms"] for v in out.values())
    result(3, best < 1000, f"reset() cloned a {size} template database (10k rows; the copy had {n}) in a median "
           f"{out['file_copy']['median_ms']} ms with FILE_COPY, {out['wal_log']['median_ms']} ms with WAL_LOG "
           f"(10 each, Postgres 17); one database per episode, dropped after", timings=out)


# ---- points 4 to 7: Claude Code through the harness adapter, against a model proxy -----------------------------

def proxy_app():
    """A stand-in for the ladder's proxy (S-178, plan step 3): records each model call with the episode id from its
    header, and answers as a skill would (no model): a tool_use block for the env's tool, then final text."""
    app = FastAPI()

    def answer(body: dict) -> tuple[list[dict], str]:
        tools = [t["name"] for t in body.get("tools", [])]
        last = body["messages"][-1]
        after_tool = isinstance(last.get("content"), list) and any(b.get("type") == "tool_result"
                                                                   for b in last["content"])
        target = next((t for t in tools if t.endswith("note_add")), None)
        if target and not after_tool:
            return [{"type": "tool_use", "id": "toolu_" + uuid.uuid4().hex[:20], "name": target,
                     "input": {"body": "written by a skill through Claude Code"}}], "tool_use"
        return [{"type": "text", "text": "Done: the note is in." if after_tool else "ok"}], "end_turn"

    def sse(msg: dict):
        def ev(name, data):
            return f"event: {name}\ndata: {json.dumps({'type': name, **data})}\n\n"
        head = {**msg, "content": [], "stop_reason": None}
        yield ev("message_start", {"message": head})
        for i, b in enumerate(msg["content"]):
            if b["type"] == "text":
                yield ev("content_block_start", {"index": i, "content_block": {"type": "text", "text": ""}})
                yield ev("content_block_delta", {"index": i, "delta": {"type": "text_delta", "text": b["text"]}})
            else:
                yield ev("content_block_start", {"index": i, "content_block": {**b, "input": {}}})
                yield ev("content_block_delta", {"index": i, "delta": {"type": "input_json_delta",
                                                                       "partial_json": json.dumps(b["input"])}})
            yield ev("content_block_stop", {"index": i})
        yield ev("message_delta", {"delta": {"stop_reason": msg["stop_reason"], "stop_sequence": None},
                                   "usage": {"output_tokens": 5}})
        yield ev("message_stop", {})

    @app.post("/v1/messages/count_tokens")
    async def count(req: Request):
        return {"input_tokens": 10}

    @app.post("/v1/messages")
    async def messages(req: Request):
        body = await req.json()
        content, stop = answer(body)
        ep = req.headers.get("x-episode-id")
        sql(LIVE, "insert into model_call(episode, path, kind, has_tools) values (%s, %s, %s, %s)",
            (ep, req.url.path, content[0]["type"], bool(body.get("tools"))))
        msg = {"id": "msg_" + uuid.uuid4().hex[:20], "type": "message", "role": "assistant",
               "model": body.get("model", "trial"), "content": content, "stop_reason": stop, "stop_sequence": None,
               "usage": {"input_tokens": 10, "output_tokens": 5}}
        if body.get("stream"):
            return StreamingResponse(sse(msg), media_type="text/event-stream")
        return JSONResponse(msg)

    @app.api_route("/{path:path}", methods=["GET", "POST", "HEAD"])
    async def other(path: str, req: Request):
        sql(LIVE, "insert into model_call(episode, path, kind, has_tools) values (%s, %s, 'other', false)",
            (req.headers.get("x-episode-id"), "/" + path))
        return JSONResponse({"error": "not in the trial"}, status_code=404)
    return app


class ClaudeCodeAdapter(AgenticHarnessAdapter):
    """RFC 005's adapter for Claude Code (none ships with openenv 0.12.0): one `claude -p` per turn, resumed by
    session id; its own tools off (`--tools ""`), only the environment's tools over the bridge (`--mcp-config`,
    `--strict-mcp-config`); model calls to ANTHROPIC_BASE_URL with the episode id in a header."""
    BUILTIN_TOOL_NAMES = frozenset({"Bash", "Read", "Edit", "Write", "Glob", "Grep", "WebFetch", "WebSearch", "Task"})

    def __init__(self, config: HarnessConfig, base_url: str):
        super().__init__(config)
        self.base_url, self.episode_id, self.session = base_url, None, None
        self.home = self.mcp_file = None

    async def inject_tools(self, tools, bridge_url=None):
        self.home = tempfile.mkdtemp(prefix="cc-")
        self.mcp_file = os.path.join(self.home, "mcp.json")
        with open(self.mcp_file, "w") as f:
            json.dump({"mcpServers": {"env": {"type": "http", "url": bridge_url}}}, f)

    async def start(self, working_directory):
        self.session = str(uuid.uuid4())
        self.turns = 0

    async def stop(self):
        if self.home:
            shutil.rmtree(self.home, ignore_errors=True)
            self.home = None

    async def is_alive(self):
        return self.home is not None

    async def send_message_streaming(self, message: str) -> AsyncIterator[HarnessEvent]:
        env = {**{k: v for k, v in os.environ.items() if k not in ("POSTGRES_PASSWORD",)},
               "HOME": self.home, "ANTHROPIC_BASE_URL": self.base_url, "ANTHROPIC_API_KEY": "trial",
               "ANTHROPIC_CUSTOM_HEADERS": f"X-Episode-Id: {self.episode_id}", "DISABLE_AUTOUPDATER": "1",
               "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}
        cmd = ["claude", "-p", message, "--bare", "--output-format", "stream-json", "--verbose", "--tools", "",
               "--mcp-config", self.mcp_file, "--strict-mcp-config", "--allowedTools", "mcp__env__*",
               "--model", self.config.model or "claude-haiku-5-5", "--max-turns", "4"]
        cmd += ["--resume", self.session] if self.turns else ["--session-id", self.session]
        self.turns += 1
        proc = await asyncio.create_subprocess_exec(*cmd, env=env, cwd=self.home, stdout=subprocess.PIPE,
                                                    stderr=subprocess.PIPE)
        final, err = "", ""
        async for raw in proc.stdout:
            try:
                ev = json.loads(raw)
            except ValueError:
                continue
            if ev.get("type") == "assistant":
                for b in ev["message"]["content"]:
                    if b["type"] == "tool_use":
                        yield HarnessEvent(type=HarnessEventType.TOOL_CALL, data={"name": b["name"], "input": b["input"]})
                    elif b["type"] == "text":
                        yield HarnessEvent(type=HarnessEventType.TEXT_OUTPUT, data={"text": b["text"]})
            elif ev.get("type") == "user":
                for b in ev["message"]["content"]:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        yield HarnessEvent(type=HarnessEventType.TOOL_RESULT, data={"content": b.get("content")})
            elif ev.get("type") == "result":
                final = ev.get("result", "") or ""
                err = "" if not ev.get("is_error") else str(ev.get("subtype"))
        await proc.wait()
        if proc.returncode and not final:
            err = err or (await proc.stderr.read()).decode()[-400:]
        if err:
            yield HarnessEvent(type=HarnessEventType.ERROR, data={"error": err})
        yield HarnessEvent(type=HarnessEventType.TURN_COMPLETE, data={"response": final, "done": True})


class NoteWritten(Rubric):
    """1.0 when the episode's note is in the database."""
    def __init__(self, env):
        super().__init__()
        self.env = env

    def forward(self, action, observation) -> float:
        n = sql(LIVE, "select count(*) from note where episode = %s", (self.env.state.episode_id,), fetch=True)[0][0]
        return 1.0 if n else 0.0


class ClaudeCodeNotesEnv(HarnessEnvironment):
    """The harness environment: Claude Code is the agent, the notes tools are its only tools."""
    def __init__(self, base_url: str):
        mcp = FastMCP("notes")
        env = self

        @mcp.tool
        def note_add(body: str) -> str:
            """Add a note to the shared notebook."""
            (nid,), = sql(LIVE, "insert into note(session, episode, body) values ('claude-code', %s, %s) returning id",
                          (env.state.episode_id, body), fetch=True)
            return f"noted #{nid}"

        super().__init__(ClaudeCodeAdapter(HarnessConfig(name="claude-code", command=["claude"],
                                                         working_directory="/tmp"), base_url), mcp=mcp)
        self.rubric = NoteWritten(self)

    async def reset_async(self, seed=None, episode_id=None, **kw):
        self.adapter.episode_id = episode_id = episode_id or uuid.uuid4().hex
        return await super().reset_async(seed=seed, episode_id=episode_id, **kw)


async def p47():
    sql(LIVE, "truncate model_call, outcome")
    srv = serve(proxy_app(), 8766)

    def attach(rubric, action, observation, score):
        # point 7: the rubric's score becomes the outcome of every model call of the episode, afterwards
        sql(LIVE, "insert into outcome(episode, score) values (%s, %s) on conflict (episode) do update set "
            "score = excluded.score", (rubric.env.state.episode_id, score))
    try:
        env = ClaudeCodeNotesEnv("http://127.0.0.1:8766")
        env.rubric.register_forward_hook(attach)
        obs = await env.reset_async()
        ep = obs.metadata["episode_id"]
        step = await env.step_async(HarnessAction(message="Write a note saying hello, then tell me you did."))
        await env.close_async() if hasattr(env, "close_async") else env.close()
    finally:
        srv.should_exit = True
    md = step.metadata or {}
    events = md.get("turn_events") or []
    kinds = [e.get("type") if isinstance(e, dict) else str(e) for e in events]
    calls = sql(LIVE, "select path, kind, has_tools, episode from model_call order by id", fetch=True)
    notes = sql(LIVE, "select body from note where episode = %s", (ep,), fetch=True)
    tool_calls = [k for k in kinds if "tool_call" in k]
    response = md.get("response") or getattr(step, "response", None) or ""
    result(4, bool(notes), f"Claude Code 2.1.311 ran as an OpenEnv HarnessEnvironment turn through a 90-line "
           f"AgenticHarnessAdapter (openenv ships none for Claude Code), its own tools off, and called the env's "
           f"tool over OpenEnv's loopback MCP bridge: notes written {len(notes)}; events {kinds}",
           injected=obs.metadata.get("injected_tools"), stderr_or_error=[e for e in events if 'error' in str(e)][:2])
    msgs = [c for c in calls if c[0] == "/v1/messages"]
    tagged = [c for c in msgs if c[3] == ep]
    result(5, bool(msgs) and len(tagged) == len(msgs), f"ANTHROPIC_BASE_URL sent all {len(msgs)} /v1/messages "
           f"calls to the proxy; {len(tagged)} carried the episode id in X-Episode-Id (ANTHROPIC_CUSTOM_HEADERS); "
           f"other paths: {sorted({c[0] for c in calls if c[0] != '/v1/messages'})}",
           calls=[list(c[:3]) for c in calls])
    kinds_sent = [c[1] for c in msgs]
    result(6, "tool_use" in kinds_sent and bool(notes) and "note is in" in str(response) + str(md),
           f"the proxy answered with no model: a tool_use block (streamed) that Claude Code executed against the env "
           f"(note written), then final text that ended the turn: response {response!r}", sent=kinds_sent,
           step_reward=step.reward)
    rows = sql(LIVE, "select count(*), count(o.score), min(o.score) from model_call m left join outcome o "
               "using (episode) where m.episode = %s", (ep,), fetch=True)[0]
    result(7, rows[0] > 0 and rows[0] == rows[1], f"the rubric (NoteWritten, score {rows[2]}) ran at step's end; "
           f"a forward hook wrote it as the episode's outcome; {rows[1]}/{rows[0]} of the episode's model calls "
           f"join to it by episode id (as env.outcome does, S-183)", episode=ep)


def facts():
    import importlib.metadata as md
    import mcp.types as t
    print(json.dumps({"point": "mcp", "openenv": md.version("openenv"), "mcp": md.version("mcp"),
                      "fastmcp": md.version("fastmcp"), "mcp_latest_protocol": t.LATEST_PROTOCOL_VERSION,
                      "task_status_input_required": hasattr(t, "TASK_STATUS_INPUT_REQUIRED"),
                      "mrtr_resultType": "resultType" in open(t.__file__).read()}), flush=True)


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    setup()
    try:
        if what in ("all", "facts"):
            facts()
        if what in ("all", "p1", "p2"):
            asyncio.run(p1_p2())
        if what in ("all", "p3"):
            p3()
        if what in ("all", "p47"):
            asyncio.run(p47())
    finally:
        teardown()
