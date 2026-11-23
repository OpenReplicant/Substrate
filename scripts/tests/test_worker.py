"""The worker's loop (plan step 1, S-163). The pure parts need no database: run_task with a scripted model, the stub MCP
server and the trial's stub OpenAI server. The environment parts (setup, the queue, the gate on ask_companion) run in a
throwaway database when ADMIN_URL is set, and are skipped otherwise.
It should:
- do a tool round trip: the model asks for `recall`, the result goes back, the answer cites a claim id the recall showed
- let the gate answer instead of the model (M-17): the model is not called, skipped_calls counts it; a gate that
  fails never leads to a model call
- stop at the step limit with ok false, never loop on
- refuse paths outside the workspace (.., absolute, a link), and write inside it
- trim old tool results to stay in the context budget, keeping the system message, the task and the latest turns
- count a made-up claim id as not cited; turn bad arguments and unknown tools into results the model can read
- offer only the memory profile's tools from an MCP server, and reach the real chat endpoint with the caller's key
- (database) accept a task from the queue, publish worker.task.done, reply, and keep ask_companion waiting for the owner

    scripts/test.sh scripts/tests/test_worker.py      # in the kernel's image, which has the `mcp` SDK
"""
import asyncio
import importlib.util
import json
import os
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

from environment import worker as w  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print(("ok  " if ok else "FAIL"), name, "" if ok else detail)


def scripted(*steps):
    """A model that answers with the given steps in order (then repeats the last) and records what it was sent."""
    seen = []

    async def model(messages, specs):
        seen.append((json.loads(json.dumps(messages)), [s["function"]["name"] for s in specs]))
        return steps[min(len(seen), len(steps)) - 1]
    model.seen = seen
    return model


def call(name, **args):
    return {"content": None, "tool_calls": [{"id": f"c{name}", "name": name, "arguments": json.dumps(args)}]}


def say(text):
    return {"content": text, "tool_calls": []}


def says_nothing():
    """A model that must not be called."""
    async def model(messages, specs):
        raise AssertionError("the model was called")
    return model


def run(coro):
    return asyncio.run(coro)


async def with_memory(fn, only=w.MEMORY_TOOLS):
    stub = str(ROOT / "scripts/tests/stub_memory_mcp.py")
    async with w.McpTools([sys.executable, stub], dict(os.environ), only) as t:
        return await fn(t)


def main():
    ws = tempfile.mkdtemp()
    tools = w.Tools(ws, ask=lambda t: "proposed, waiting for the owner")

    # the round trip, with a real MCP server over stdio
    async def trip(t):
        m = scripted(call("recall", question="where is the pump"), say("The pump is on shelf B (#abc12345)."))
        r = await w.run_task("where is the pump", m, w.Tools(ws, mcp=t.session, mcp_specs=t.specs))
        return r, m
    r, m = run(with_memory(trip))
    check("a tool round trip: recall, its result back, the answer", r["ok"] and r["text"].startswith("The pump") and r["model_calls"] == 2
          and r["skipped_calls"] == 0, r)
    check("the answer's claim id is cited, as the recall showed it", r["cited"] == ["#abc12345"], r)
    check("the tool result reached the model", any(x["role"] == "tool" and "shelf B" in x["content"] for x in m.seen[1][0]))
    check("only the memory profile's tools are offered from the MCP server", "recall" in m.seen[0][1] and "remember" in m.seen[0][1]
          and "secret_admin" not in m.seen[0][1], m.seen[0][1])

    # the gate: M-17's seam
    m = scripted(say("never"))
    r = run(w.run_task("ping", m, tools, gate=lambda s: "pong" if s["task"] == "ping" else None))
    check("a gate answer needs no model call, and is counted", r["text"] == "pong" and r["ok"] and not m.seen
          and r["model_calls"] == 0 and r["skipped_calls"] == 1, r)
    m = scripted(call("now"), say("done"))
    r = run(w.run_task("t", m, tools, gate=lambda s: "from the skill" if s["step"] == 1 else None))
    check("a gate may answer after a tool step: one call made, one skipped", r["text"] == "from the skill" and r["model_calls"] == 1
          and r["skipped_calls"] == 1 and len(m.seen) == 1, r)
    m = scripted(say("hello"))
    r = run(w.run_task("t", m, tools))
    check("with no gate the model is called, and counted", r["text"] == "hello" and r["model_calls"] == 1 and r["skipped_calls"] == 0, r)

    def broken(state):
        raise RuntimeError("boom")
    m = scripted(say("x"))
    r = run(w.run_task("t", m, tools, gate=broken))
    check("a gate that fails ends the task without calling the model", not r["ok"] and not m.seen and "boom" in r["text"], r)

    # bounds
    m = scripted(call("now"))
    r = run(w.run_task("loop forever", m, tools, max_steps=3))
    check("the step limit ends a loop, not ok", not r["ok"] and r["model_calls"] == 3 and "3 steps" in r["text"], r)

    async def failing(messages, specs):
        raise ConnectionError("gateway down")
    r = run(w.run_task("t", failing, tools))
    check("a failing model call is the task's failed result", not r["ok"] and "gateway down" in r["text"] and r["model_calls"] == 1, r)

    # the workspace
    Path(ws, "a.txt").write_text("hello")
    os.symlink("/etc", os.path.join(ws, "link"))
    t = lambda name, **a: run(tools.call(name, a))
    check("reads inside the workspace", t("read_file", path="a.txt") == "hello")
    check("lists it", "a.txt" in t("list_dir"))
    check("refuses .. out of it", t("read_file", path="../etc/passwd").startswith("refused"))
    check("refuses an absolute path", t("read_file", path="/etc/passwd").startswith("refused"))
    check("refuses a link out of it", t("read_file", path="link/passwd").startswith("refused") and t("list_dir", path="link").startswith("refused"))
    check("refuses writing outside it", t("write_file", path="../evil", content="x").startswith("refused")
          and t("write_file", path="/tmp/evil-worker-test", content="x").startswith("refused")
          and not Path("/tmp/evil-worker-test").exists())
    check("writes inside it, folders made", t("write_file", path="sub/b.txt", content="hi").startswith("wrote")
          and Path(ws, "sub/b.txt").read_text() == "hi")
    check("a missing argument is a result, not a crash", t("read_file").startswith("error: missing"))

    # the model's mistakes
    m = scripted({"content": None, "tool_calls": [{"id": "1", "name": "read_file", "arguments": "{not json"},
                                                  {"id": "2", "name": "nosuch", "arguments": "{}"}]}, say("ok"))
    r = run(w.run_task("t", m, tools))
    tool_msgs = [x["content"] for x in m.seen[1][0] if x["role"] == "tool"]
    check("bad JSON arguments and unknown tools are results the model reads", r["ok"] and len(tool_msgs) == 2
          and all(x.startswith("error") for x in tool_msgs), tool_msgs)
    m = scripted(call("now"), say("see #deadbeef and #abc12345"))

    async def seeded(t):
        return await w.run_task("t", m, w.Tools(ws, mcp=t.session, mcp_specs=t.specs))
    m = scripted(call("recall", question="q"), say("see #deadbeef and #abc12345"))
    r = run(with_memory(seeded))
    check("an id the model made up is not counted as cited", r["cited"] == ["#abc12345"], r)

    # context trimming
    big = "x" * 6000
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "task"}]
    for i in range(6):
        msgs += [{"role": "assistant", "content": None, "tool_calls": [{"id": str(i)}]}, {"role": "tool", "tool_call_id": str(i), "content": big}]
    out = w.trim(msgs, 3000)
    check("old tool results are trimmed to fit", w.tokens(out) <= 3000 and out[3]["content"].startswith("[trimmed"), w.tokens(out))
    check("the system message, the task and the latest turn are kept", out[0] == msgs[0] and out[1] == msgs[1] and out[-1] == msgs[-1])
    check("the transcript itself is not changed", msgs[3]["content"] == big)
    check("short conversations are left alone", w.trim(msgs[:4], 10**6) == msgs[:4])
    m = scripted(*([call("now")] * 3), say("fine"))
    r = run(w.run_task("t", m, tools, budget=400))
    check("the loop sends the model trimmed history", r["ok"] and all(w.tokens(s[0]) <= 400 or len(s[0]) <= 4 for s in m.seen))

    # the login file's host is the stack's db
    f = Path(ws, "login.env")
    f.write_text("KK_DATABASE_URL=postgresql://kkr_worker:pw@127.0.0.1:5432/kernel\n")
    e = w.kernel_env(str(f))
    check("the kernel login's host becomes db, the profile is memory", e["KK_DATABASE_URL"] == "postgresql://kkr_worker:pw@db:5432/kernel"
          and e["KK_PROFILE"] == "memory", e)

    chat_endpoint()
    database()
    print(f"{sum(checks)}/{len(checks)} checks passed")
    sys.exit(0 if all(checks) else 1)


def chat_endpoint():
    """The real client against the trial's stub OpenAI-compatible server and its stub MCP server: tools, the key, two calls."""
    try:
        import openai  # noqa: F401
    except ImportError:
        print("skip  the chat endpoint (the openai package is not installed here)")
        return
    d = ROOT / "scripts/trials/offline-agent"
    spec = importlib.util.spec_from_file_location("stub_llm", d / "stub_llm.py")
    stub = importlib.util.module_from_spec(spec)
    log = tempfile.mktemp()
    os.environ["STUB_LOG"] = log
    spec.loader.exec_module(stub)
    # HTTP/1.1 keeps the connection open, as the gateway does: a pooled connection from one task's event loop is what a
    # client shared across asyncio.run calls trips on
    srv = ThreadingHTTPServer(("127.0.0.1", 0), type("H11", (stub.H,), {"protocol_version": "HTTP/1.1"}))
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    model = w.openai_model(f"http://127.0.0.1:{srv.server_port}", "stub-key", "local/gemma")

    async def go():
        async with w.McpTools([sys.executable, str(d / "stub_mcp.py")], dict(os.environ), ("add",)) as t:
            return await w.run_task("What is 2 + 3? Use the add tool.", model, w.Tools(tempfile.mkdtemp(), mcp=t.session, mcp_specs=t.specs))
    r = run(go())
    r2 = run(go())          # a second task, its own event loop, the same model: the client must not be the first loop's
    srv.shutdown()
    seen = [json.loads(x) for x in open(log)][:2]
    check("the OpenAI client does the round trip with the tool", r["ok"] and r["text"] == "The answer is 5." and r["model_calls"] == 2, r)
    check("a second task in a new event loop reuses the model (no 'Event loop is closed')", r2["ok"] and r2["model_calls"] == 2, r2)
    check("the stub saw two calls, as the model, with the key and the tools", len(seen) == 2 and seen[0]["model"] == "local/gemma"
          and seen[0]["auth"] == "Bearer stub-key" and "add" in seen[0]["tools"], seen)


def database():
    admin = os.environ.get("ADMIN_URL")
    if not admin:
        print("skip  the environment parts (no ADMIN_URL)")
        return
    import psycopg
    from environment import db as envdb
    from environment import Env
    name, login = f"worker_test_{os.getpid()}", f"worker_login_{os.getpid()}"
    with psycopg.connect(admin, autocommit=True) as a:
        a.execute(f"create database {name}")
    url = admin.rsplit("/", 1)[0] + "/" + name
    try:
        with psycopg.connect(url, autocommit=True) as c:
            envdb.migrate(c)
            c.execute(f"create role {login} login password 'test-only'")
            c.execute(f"grant env_agent to {login}")
            owner = Env(c)
            w.setup(owner, login, blocks=str(ROOT / "blocks/examples"))
            check("each world-changing block in WORKER_BLOCKS gets its actuator, free", c.execute(
                "select gate from env.actuator where name = 'blocks.write_note'").fetchone() == ("free",))
            check("the gate on ask_companion is propose, reply is free", dict(c.execute("select name, gate from env.actuator where name like 'worker.%'").fetchall())
                  == {"worker.reply": "free", "worker.ask_companion": "propose"})
            host = url.split("@", 1)[1].split("/", 1)[0]
            ws = tempfile.mkdtemp()
            os.environ["WORKER_WORKSPACE"] = ws
            with psycopg.connect(f"postgresql://{login}:test-only@{host}/{name}", autocommit=True) as ac:
                me = Env(ac)
                owner.publish("worker.owner.message", {"text": "ask the companion about tax"}, "owner")
                msgs = me.read(w.QUEUE, 60, 1)
                check("the worker reads the owner's message from its queue", [x["key"] for x in msgs] == ["worker.owner.message"], msgs)
                model = scripted(call("ask_companion", text="tax question"), say("I asked; waiting."))
                out = w.handle(me, msgs[0], model)
                check("the task is done, with its counts", out["ok"] and out["model_calls"] == 2, out)
                tool_result = [x for x in model.seen[1][0] if x["role"] == "tool"][0]["content"]
                check("ask_companion is gated: the model is told it waits for the owner", tool_result == "proposed, waiting for the owner", tool_result)
                done = c.execute("select body from env.signal where key = 'worker.task.done'").fetchone()[0]
                check("worker.task.done carries text, calls and cited", done["text"] == "I asked; waiting." and done["model_calls"] == 2
                      and done["skipped_calls"] == 0 and done["cited"] == [], done)
                check("the reply is applied as shown", c.execute("select status from env.action where actuator = 'worker.reply'").fetchone()[0] == "applied")
                prop = c.execute("select id, status from env.action where actuator = 'worker.ask_companion'").fetchone()
                check("the hand-off waits for the owner and reached no one", prop[1] == "proposed"
                      and not c.execute("select 1 from env.signal where key = 'companion.owner.message'").fetchone())
                owner.decide(prop[0], True, "owner")
                w.apply_companion(me)
                check("approved, it reaches the companion as an owner message", c.execute(
                    "select body from env.signal where key = 'companion.owner.message'").fetchone()[0] == {"text": "tax question"})
                check("it may not decide its own proposal", refused(lambda: me.decide(prop[0], True, "owner")))
                os.environ["WORKER_BLOCKS"] = str(ROOT / "blocks/examples")
                gate = w.skills(me)
                out = run(w.run_task("save a note called t1: one two three", says_nothing(), w.Tools(ws), gate=gate))
                check("a task matching a plan runs it under the worker's login, no model call", out["ok"] and out["model_calls"] == 0
                      and out["skipped_calls"] == 1 and out["text"] == "Saved notes/t1.txt (3 words).", out)
                check("the block's action is applied (its queue is the worker's to close)", c.execute(
                    "select status from env.action where actuator = 'blocks.write_note'").fetchall() == [("applied",)])
    finally:
        with psycopg.connect(admin, autocommit=True) as a:
            a.execute(f"drop database {name} with (force)")
            a.execute(f"drop role if exists {login}")


def refused(fn):
    import psycopg
    try:
        fn()
    except psycopg.Error:
        return True
    return False


if __name__ == "__main__":
    main()
