"""The worker (plan step 1, S-163): an offline agent on the local model. Its loop is our own (S-162): the `mcp` SDK for
the Knowledge Kernel's `memory` profile and the `openai` client for the gateway's OpenAI-compatible endpoint.

    python3 -m environment.worker setup    # its actuators, queues and grants (scripts/db.py init, as the owner)
    python3 -m environment.worker run      # in the worker's container: read the queue, run each task, reply

Streams (signals, under worker.*):
    owner.message     what the owner says on the UI's #/worker page ({"text"})
    task              a task another process hands it ({"text"})
    task.done         a task's outcome: {"text", "ok", "model_calls", "skipped_calls", "steps", "cited", "task"}

Actuators:
    reply           free     a message to the owner ({"text"}); the page shows it
    ask_companion   propose  hand the task to the companion (Claude, in the cloud: the request leaves this machine,
                             docs/privacy.md P3), so it waits for the owner; applied by `run` as a
                             companion.owner.message once approved

The loop (`run_task`) is the seam for MetaSoar's M-17, the model is called only at impasses: before EVERY model call it
asks `gate(state)`; a string answers the task without the model (a compiled skill), None lets the model be called.
The loop counts the model calls and the skipped calls itself. Settings (environment): GATEWAY_URL, WORKER_KEY (the
caller `worker:loop`, local models only), WORKER_MODEL (local/slow), WORKER_WORKSPACE (/workspace),
WORKER_MAX_STEPS (8), WORKER_CONTEXT_TOKENS (11000 of the model's 16k), WORKER_MAX_TOKENS (1024),
WORKER_REASONING (empty), WORKER_MCP_COMMAND (kernel-mcp), WORKER_LOGIN_FILE (/login, from scripts/kernel.sh login worker).
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import re
import shlex
import sys
import time
from pathlib import Path
from typing import Awaitable, Callable

ENV = "worker"
QUEUE = "worker_loop"
PATTERNS = ["worker.owner.message", "worker.task"]
ACTUATORS = {
    "reply": ("free", "A message to the owner, shown on the UI's page. Input: {\"text\": \"...\"}."),
    "ask_companion": ("propose", "Hand a request to the companion (Claude, in the cloud, with its tools). It leaves this "
                      "machine, so the owner decides. Input: {\"text\": \"the request, complete\"}."),
}
LOGIN = "worker"
SOURCE = "substrate:worker"
MEMORY_TOOLS = ("recall", "remember", "explain", "changes_since")

SYSTEM = """You are an offline assistant on the owner's machine. Work in small steps and use your tools.
Before you answer a question, call recall to see what is already known. Cite the claim ids (the #handles) that
your answer rests on. When you have worked something out that is worth keeping, call remember with it and its
source. Use read_file, list_dir and write_file only for the workspace. Say plainly when you do not know.
If the task needs the internet or more than you can do, say so; ask_companion hands it to a larger assistant, with the
owner's approval. Finish with a short answer."""

# ---- settings


def setting(name: str, default: str = "") -> str:
    return os.environ.get(name) or default


# ---- the workspace: three file tools confined to one directory

class Refused(Exception):
    """A path outside the workspace, or too large."""


MAX_FILE = 100_000


def safe_path(root: str | Path, rel: str) -> Path:
    """`rel` resolved under `root`; anything that lands outside it (an absolute path, .., a link) is refused."""
    base = Path(root).resolve()
    if not isinstance(rel, str) or "\x00" in rel:
        raise Refused("not a path")
    p = (base / rel).resolve()
    if p != base and base not in p.parents:
        raise Refused(f"{rel!r} is outside the workspace")
    return p


def _read_file(root, path: str) -> str:
    p = safe_path(root, path)
    if not p.is_file():
        raise Refused(f"{path!r} is not a file")
    return p.read_text(errors="replace")[:MAX_FILE]


def _list_dir(root, path: str = ".") -> str:
    p = safe_path(root, path or ".")
    if not p.is_dir():
        raise Refused(f"{path!r} is not a folder")
    return "\n".join(sorted(c.name + ("/" if c.is_dir() else "") for c in p.iterdir())) or "(empty)"


def _write_file(root, path: str, content: str) -> str:
    p = safe_path(root, path)
    if p == Path(root).resolve() or p.is_dir():
        raise Refused(f"{path!r} is a folder")
    if len(content) > MAX_FILE:
        raise Refused(f"too large (at most {MAX_FILE} characters)")
    p.parent.mkdir(parents=True, exist_ok=True)
    safe_path(root, str(p.parent.relative_to(Path(root).resolve())))     # created folders stay inside
    p.write_text(content)
    return f"wrote {len(content)} characters to {path}"


def _spec(name: str, description: str, props: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": props, "required": required}}}


S = {"type": "string"}
LOCAL_SPECS = [
    _spec("read_file", "Read a text file in the workspace.", {"path": S}, ["path"]),
    _spec("list_dir", "List a folder in the workspace (default: its top).", {"path": S}, []),
    _spec("write_file", "Write a text file in the workspace (replaces it).", {"path": S, "content": S}, ["path", "content"]),
    _spec("now", "The current date and time.", {}, []),
    _spec("ask_companion", "Hand a request to the larger cloud assistant. The owner must approve it; you get no answer "
          "now. Say the request completely.", {"text": S}, ["text"]),
]


class Tools:
    """The tools the loop offers: the local ones, and an MCP session's. `specs` are OpenAI function specs; `call`
    returns text, never raises (a failure is a result the model can read)."""

    def __init__(self, workspace: str | Path, ask: Callable[[str], str] | None = None, mcp=None, mcp_specs: list | None = None):
        self.workspace, self.ask, self.mcp = workspace, ask, mcp
        self.specs = [s for s in LOCAL_SPECS if s["function"]["name"] != "ask_companion" or ask] + list(mcp_specs or [])

    async def call(self, name: str, args) -> str:
        if not isinstance(args, dict):
            return "error: arguments must be a JSON object"
        try:
            if name == "read_file":
                return _read_file(self.workspace, args["path"])
            if name == "list_dir":
                return _list_dir(self.workspace, args.get("path", "."))
            if name == "write_file":
                return _write_file(self.workspace, args["path"], str(args["content"]))
            if name == "now":
                return dt.datetime.now().astimezone().isoformat(timespec="seconds")
            if name == "ask_companion" and self.ask:
                return self.ask(str(args["text"]))
            if self.mcp is not None and any(s["function"]["name"] == name for s in self.specs):
                res = await self.mcp.call_tool(name, args)
                text = "".join(getattr(c, "text", "") for c in res.content)
                return ("error: " if res.is_error else "") + text
        except Refused as x:
            return f"refused: {x}"
        except KeyError as x:
            return f"error: missing argument {x}"
        except Exception as x:                                       # noqa: BLE001 - a tool's failure is the model's to read
            return f"error: {type(x).__name__}: {x}"
        return f"error: no tool {name}"


class McpTools:
    """The kernel's `memory` profile over stdio: `async with McpTools(command, env) as t: Tools(ws, mcp=t.session,
    mcp_specs=t.specs)`."""

    def __init__(self, command: list[str], env: dict[str, str], only: tuple[str, ...] = MEMORY_TOOLS):
        self.command, self.env, self.only = command, env, only

    async def __aenter__(self):
        from contextlib import AsyncExitStack
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        self.stack = AsyncExitStack()
        r, w = await self.stack.enter_async_context(stdio_client(
            StdioServerParameters(command=self.command[0], args=self.command[1:], env=self.env)))
        self.session = await self.stack.enter_async_context(ClientSession(r, w))
        await self.session.initialize()
        self.specs = [_spec(t.name, t.description or "", t.input_schema, []) for t in (await self.session.list_tools()).tools
                      if t.name in self.only]
        return self

    async def __aexit__(self, *exc):
        await self.stack.aclose()


def kernel_env(login_file: str | None = None) -> dict[str, str]:
    """The kernel-mcp process's environment: PATH, the worker's kernel login (the file scripts/kernel.sh login writes,
    its host rewritten from the machine's 127.0.0.1:port to the stack's db:5432) and the `memory` profile."""
    path = login_file or setting("WORKER_LOGIN_FILE", "/login")
    # in its container the login comes from .env (WORKER_KERNEL_URL, rule 4): a mounted 0600 file is not readable by the
    # container's own user under rootless Podman
    url = "" if login_file else os.environ.get("WORKER_KERNEL_URL", "")
    if not url and os.path.exists(path):
        for line in open(path):
            if line.startswith("KK_DATABASE_URL="):
                url = line.split("=", 1)[1].strip()
    url = re.sub(r"@127\.0\.0\.1:\d+/", "@db:5432/", url) if os.environ.get("WORKER_REWRITE_HOST", "1") == "1" else url
    env = {k: os.environ[k] for k in ("PATH", "HOME", "LANG") if k in os.environ}
    env.update(KK_PROFILE="memory", KK_DATABASE_URL=url)
    return env


# ---- the model: OpenAI chat completions with tools, at the gateway

Model = Callable[[list, list], Awaitable[dict]]     # (messages, tool specs) -> {"content": str|None, "tool_calls": [{"id","name","arguments"}]}


def openai_model(gateway: str | None = None, key: str | None = None, model: str | None = None) -> Model:
    from openai import AsyncOpenAI
    key, name = key or setting("WORKER_KEY"), model or setting("WORKER_MODEL", "local/slow")
    base = (gateway or setting("GATEWAY_URL", "http://gateway:8080")).rstrip("/") + "/v1"
    clients: dict = {}       # one client per event loop: each task is its own asyncio.run, and a client's connections
                             # belong to the loop that opened them ("Event loop is closed" on the next task otherwise)

    def client():
        loop = asyncio.get_running_loop()
        if clients.get("loop") is not loop:
            clients.update(loop=loop, client=AsyncOpenAI(base_url=base, api_key=key or "none", default_headers={"x-bf-vk": key},
                                                         timeout=600, max_retries=1))
        return clients["client"]
    extra = {"reasoning_effort": setting("WORKER_REASONING")} if setting("WORKER_REASONING") else None

    async def call(messages: list, specs: list) -> dict:
        r = await client().chat.completions.create(
            model=name, messages=messages, tools=specs or None, max_tokens=int(setting("WORKER_MAX_TOKENS", "1024")),
            temperature=0.2, extra_body=extra, extra_headers={"x-wb-call": f"worker-{time.time_ns()}"})
        m = r.choices[0].message
        return {"content": m.content, "tool_calls": [{"id": c.id, "name": c.function.name, "arguments": c.function.arguments}
                                                      for c in (m.tool_calls or [])]}
    return call


# ---- the loop

Gate = Callable[[dict], "str | None"]
TOOL_RESULT_CHARS = 4000


def tokens(messages: list) -> int:
    """A cheap estimate (about 3.5 characters a token): the loop only needs to stay clear of the context's end."""
    return sum(len(json.dumps(m, ensure_ascii=False)) for m in messages) * 2 // 7


def trim(messages: list, budget: int) -> list:
    """Messages within `budget` tokens: the oldest tool results are replaced by a note, one at a time, until it fits.
    The system message, the task and the latest messages are never touched. A copy; the transcript is kept whole."""
    out = [dict(m) for m in messages]
    for m in out[2:-2]:
        if tokens(out) <= budget:
            break
        if m.get("role") == "tool" and not m["content"].startswith("[trimmed"):
            m["content"] = f"[trimmed: {len(m['content'])} characters of an earlier result]"
    return out


IDS = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|#[0-9a-f]{6,12}")


def cited(tool_results: list[str], answer: str) -> list[str]:
    """Claim ids (uuids, or the #handles a briefing shows) in the answer that a tool result also shows, so an id
    the model made up is not counted."""
    seen = {i for r in tool_results for i in IDS.findall(r)}
    out: list[str] = []
    for i in IDS.findall(answer):
        if i in seen and i not in out:
            out.append(i)
    return out


async def run_task(task: str, model: Model, tools: Tools, gate: Gate | None = None, max_steps: int | None = None,
                   budget: int | None = None, system: str = SYSTEM) -> dict:
    """One task to its answer. Before every model call `gate(state)` may return the answer instead (M-17); the loop
    counts model_calls and skipped_calls. state: {task, step, messages, tool_results, model_calls}."""
    gate = gate or (lambda state: None)
    max_steps = max_steps or int(setting("WORKER_MAX_STEPS", "8"))
    budget = budget or int(setting("WORKER_CONTEXT_TOKENS", "11000"))
    msgs: list = [{"role": "system", "content": system}, {"role": "user", "content": task}]
    results: list[str] = []
    out = {"text": "", "ok": False, "model_calls": 0, "skipped_calls": 0, "steps": 0, "cited": []}

    def finish(text: str, ok: bool) -> dict:
        out.update(text=text, ok=ok, cited=cited(results, text))
        return out

    for step in range(max_steps):
        out["steps"] = step + 1
        try:
            answer = gate({"task": task, "step": step, "messages": msgs, "tool_results": results, "model_calls": out["model_calls"]})
        except Exception as x:                                       # noqa: BLE001 - a broken gate must not call the model
            return finish(f"the gate failed: {type(x).__name__}: {x}", False)
        if answer is not None:
            out["skipped_calls"] += 1
            return finish(str(answer), True)
        out["model_calls"] += 1
        try:
            m = await model(trim(msgs, budget), tools.specs)
        except Exception as x:                                       # noqa: BLE001 - reported as the task's result
            return finish(f"the model call failed: {type(x).__name__}: {str(x)[:300]}", False)
        calls = m.get("tool_calls") or []
        if not calls:
            text = (m.get("content") or "").strip()
            if not text:                                             # e.g. the model spent its tokens thinking (S-171)
                return finish("the model gave no answer (it may have used its tokens thinking; WORKER_MAX_TOKENS)", False)
            return finish(text, True)
        msgs.append({"role": "assistant", "content": m.get("content"), "tool_calls": [
            {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"]}} for c in calls]})
        for c in calls:
            try:
                args = json.loads(c["arguments"] or "{}")
            except json.JSONDecodeError:
                args = None
            text = (await tools.call(c["name"], args))[:TOOL_RESULT_CHARS]
            results.append(text)
            msgs.append({"role": "tool", "tool_call_id": c["id"], "content": text})
    return finish(f"stopped after {max_steps} steps without an answer", False)


# ---- the environment: setup and run

def log(*a) -> None:
    print("worker:", *a, file=sys.stderr, flush=True)


def connect():
    import psycopg
    from environment import Env
    from environment.db import database_url
    return Env(psycopg.connect(database_url(), autocommit=True))


def setup(e, login: str = LOGIN, blocks: str = "") -> None:
    for name, (gate, text) in ACTUATORS.items():
        if e.c.execute("select 1 from env.actuator where name = %s", (f"{ENV}.{name}",)).fetchone() is None:
            e.actuator(f"{ENV}.{name}", gate, SOURCE, text)        # a gate someone changed since is kept
    # the actuator each world-changing block in WORKER_BLOCKS runs through (S-164): free, as the worker's own file tools
    # are; a gate someone changed since is kept
    made = []
    if blocks and os.path.isdir(blocks):
        from blocks import load_catalog
        for b in load_catalog(blocks).blocks.values():
            if b.changes_world:
                made.append(f"blocks.{b.name}")
                if e.c.execute("select 1 from env.actuator where name = %s", (made[-1],)).fetchone() is None:
                    e.actuator(made[-1], "free", SOURCE, b.spec.get("description"))
                # the executor closes the action (env.done), which needs the actuator's queue
                q = e.c.execute("select queue from env.actuator where name = %s", (made[-1],)).fetchone()[0]
                e.c.execute("select env.allow(%s, %s)", (q, login))
    e.subscribe(QUEUE, PATTERNS)
    for q in (QUEUE, f"act_{ENV}_reply", f"act_{ENV}_ask_companion"):
        e.c.execute("select env.allow(%s, %s)", (q, login))
    print(f"  worker: actuators {', '.join(ACTUATORS)}; queue {QUEUE}; login {login} may read them"
          + (f"; blocks through {', '.join(made)}" if made else ""))


def skills(e=None) -> Gate | None:
    """The skill ladder's first rung (S-164, M-17): plans in WORKER_BLOCKS whose trigger matches a task answer it
    without the model. Empty or missing: no gate, every task goes to the model. e: the environment a world-changing
    block's step goes through (its actuator blocks.<name>); without one such a step is refused."""
    root = setting("WORKER_BLOCKS", "")
    if not root or not os.path.isdir(root):
        return None
    from blocks import load_catalog
    from blocks.run import Executor, skill_gate
    catalog = load_catalog(root)
    log(f"skills: {len(catalog.plans)} plans from {root}")
    return skill_gate(catalog, Executor(e, SOURCE))


def handle(e, m: dict, model: Model, gate: Gate | None = None, mcp_factory=None) -> dict:
    """One queue message to its outcome: run the task, publish worker.task.done, reply. Returns the outcome."""
    body = m.get("body")
    text = body.get("text") if isinstance(body, dict) else None
    if not isinstance(text, str) or not text.strip():
        out = {"text": "a task needs text", "ok": False, "model_calls": 0, "skipped_calls": 0, "steps": 0, "cited": []}
    else:
        workspace = setting("WORKER_WORKSPACE", "/workspace")
        os.makedirs(workspace, exist_ok=True)

        def ask(request: str) -> str:
            _, status = e.act(f"{ENV}.ask_companion", {"text": request, "task": m["msg_id"]}, SOURCE)
            return {"proposed": "proposed, waiting for the owner", "queued": "queued for the companion",
                    "denied": "refused: handing work to the companion is not allowed now"}[status]

        async def go():
            if mcp_factory is None:
                return await run_task(text, model, Tools(workspace, ask), gate)
            async with mcp_factory() as t:
                return await run_task(text, model, Tools(workspace, ask, t.session, t.specs), gate)
        try:
            out = asyncio.run(go())
        except Exception as x:                                       # noqa: BLE001 - e.g. the kernel's MCP server did not start
            out = {"text": f"could not start the tools: {type(x).__name__}: {str(x)[:300]}", "ok": False, "model_calls": 0,
                   "skipped_calls": 0, "steps": 0, "cited": []}
    # reply_to: who asked, when they want the answer back (the voice head reads out its own, S-170)
    reply_to = body.get("reply_to") if isinstance(body, dict) and isinstance(body.get("reply_to"), str) else None
    e.publish(f"{ENV}.task.done", {**out, "task": text or "", "msg": m["msg_id"], **({"reply_to": reply_to} if reply_to else {})}, SOURCE)
    action, _ = e.act(f"{ENV}.reply", {"text": out["text"]}, SOURCE)
    for r in e.read(f"act_{ENV}_reply", 60, 10):
        e.done(r["action"], {"shown": True})
    return out


def apply_companion(e) -> None:
    """Approved hand-offs reach the companion as the owner-message stream it already reads."""
    for r in e.read(f"act_{ENV}_ask_companion", 60, 10):
        t = (r.get("input") or {}).get("text")
        if isinstance(t, str) and t.strip():
            e.publish("companion.owner.message", {"text": t.strip()}, "worker (approved by the owner)")
            e.done(r["action"], {"sent": True})
        else:
            e.done(r["action"], {"error": "no text"}, False)


def run() -> None:
    import psycopg
    model = openai_model()
    gate, gate_env = None, None
    # notes/ is shared with the voice head (S-171), which runs in the worker's group: group-writable, setgid
    ws = setting("WORKER_WORKSPACE", "/workspace")
    for d in (ws, os.path.join(ws, "notes")):
        try:
            os.makedirs(d, exist_ok=True)
            os.chmod(d, 0o2775)
        except OSError as x:
            log(f"workspace {d}: {x}")
    cmd = shlex.split(setting("WORKER_MCP_COMMAND", "kernel-mcp"))
    factory = lambda: McpTools(cmd, kernel_env())                    # noqa: E731
    e = None
    while True:
        try:
            e = e if e and not e.c.closed else connect()
            if gate_env is not e:                                    # the gate's executor acts on this connection
                gate, gate_env = skills(e), e
            apply_companion(e)
            for m in e.read(QUEUE, 1800, 1):
                log(f"task {m['msg_id']}: started")
                out = handle(e, m, model, gate, factory)
                e.ack(QUEUE, [m["msg_id"]])
                log(f"task {m['msg_id']}: {'done' if out['ok'] else 'failed'}, {out['model_calls']} model calls, {out['skipped_calls']} skipped")
        except psycopg.OperationalError as x:
            log(f"database: {x}; retrying")
            e = None
            time.sleep(5)
        except psycopg.Error as x:
            log(f"{type(x).__name__}: {x}")
        time.sleep(2)


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "setup":
        setup(connect())
    elif cmd == "run":
        run()
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
