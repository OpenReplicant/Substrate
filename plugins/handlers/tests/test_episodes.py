"""The step loop and episode streams (README.md, "Episodes").

Without a database: the loop on a toy environment with script handlers (terminated, truncated, escalated, ask,
an unknown handler asked). In a throwaway database: a toy package (an environment, an agent with one model
handler behind a fake gateway that keeps its own log) declared, two saved items each starting an episode, every
call recorded and metered from the gateway's record, a hand-off raised in the review lane, nothing run twice, and
an episode a gateway refusal ended run again.

    WORKBENCH_ADMIN_URL=postgresql://postgres:...@127.0.0.1:5432/postgres python3 plugins/handlers/tests/test_episodes.py
"""
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "workbench"), str(ROOT / "plugins/handlers")]
os.environ["WORKBENCH_DB"] = DB = f"workbench_test_{os.getpid()}"
os.environ.setdefault("WORKBENCH_JWT_SECRET", "m-" + "z" * 40)

import episode  # noqa: E402
from ladder import Answer, Escalate, handler  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print(("ok  " if ok else "FAIL"), name, "" if ok else detail)


class Toy:
    """Counts to a target: `add` adds one, `answer` ends it, `stop` hands it up."""

    def actions(self):
        return [{"kind": k} for k in ("add", "answer", "stop")]

    def reset(self, case, seed=0):
        self.n, self.target, self.over = 0, case["target"], False
        return [{"subject": case["id"], "property": "target", "value": self.target, "source": "case", "time": None}]

    def step(self, action):
        if self.over:
            raise RuntimeError("ended")
        k = action.get("kind")
        info, term = {}, False
        if k == "add":
            self.n += 1
        elif k == "answer":
            term = True
        elif k == "stop":
            term, info["escalated"] = True, True
        else:
            info["refused"] = k
        self.over = term or self.n >= 5
        return [{"subject": "count", "property": "n", "value": self.n, "source": "toy", "time": None}], None, term, self.n >= 5 and not term, info

    def final(self):
        return {"n": self.n}


shown = []


@handler("t-counter")
def counter(item, ask):
    shown.append(item)
    n = item["observation"][0]["value"] if item["step"] > 1 else 0
    target = (item["episode"][0]["observation"] if item["episode"] else item["observation"])[0]["value"]
    return Answer({"kind": "answer"} if n >= target else {"kind": "add"}, 1.0)


@handler("t-delegate")
def delegate(item, ask):
    return Answer({"kind": "ask", "handler": "counter"}, 1.0)


@handler("t-nobody")
def nobody(item, ask):
    return Answer({"kind": "ask", "handler": "nobody-here"}, 1.0)


@handler("t-giveup")
def giveup(item, ask):
    return Escalate("cannot")


r = episode.run(Toy(), {"id": "c1", "target": 2}, ["counter"], {"counter": "t-counter"})
check("an episode runs to its end: observation, action, step", r["end"] == "terminated" and r["final"] == {"n": 2} and r["steps"] == 3,
      (r["end"], r["final"], r["steps"]))
check("each step the handler gets the episode so far, the new observation and the actions",
      [len(i["episode"]) for i in shown] == [0, 1, 2] and shown[2]["episode"][1]["action"] == {"kind": "add"}
      and shown[0]["actions"][0] == {"kind": "add"}, [len(i["episode"]) for i in shown])
check("a log entry names who took the step", all(s["by"] == "counter" for s in r["log"]), r["log"])
r = episode.run(Toy(), {"id": "c2", "target": 99}, ["counter"], {"counter": "t-counter"})
check("an episode the environment cuts short is truncated", r["end"] == "truncated" and r["steps"] == 5, (r["end"], r["steps"]))
r = episode.run(Toy(), {"id": "c3", "target": 9}, ["counter"], {"counter": "t-counter"}, max_steps=3)
check("so is one at the loop's max_steps", r["end"] == "truncated" and r["steps"] == 3, (r["end"], r["steps"]))
r = episode.run(Toy(), {"id": "c4", "target": 1}, ["giveup"], {"giveup": "t-giveup"})
check("an escalation off the top of the route ends it as escalated", r["end"] == "escalated" and r["steps"] == 1 and not r["actions"], r)
r = episode.run(Toy(), {"id": "c5", "target": 1}, ["delegate", "counter"], {"delegate": "t-delegate", "counter": "t-counter"})
asked = [(c.handler, c.parent) for c in r["calls"]][:2]
check("ask hands the step to another handler, recorded as a call the asker made",
      r["end"] == "terminated" and asked == [("delegate", None), ("counter", 0)] and r["log"][0]["by"] == "counter", (asked, r["log"][0]))
r = episode.run(Toy(), {"id": "c6", "target": 1}, ["nobody"], {"nobody": "t-nobody"}, max_steps=2)
check("asking a handler that does not exist goes to the environment, which refuses it", r["actions"][0]["kind"] == "ask" and r["end"] == "truncated", r)

# ---- in a throwaway database: a package as an episode stream

import psycopg  # noqa: E402
from psycopg import sql  # noqa: E402

from workbench import cli  # noqa: E402
from workbench.extract import Plugins, run_extractor  # noqa: E402
import handlers_plugin as hp  # noqa: E402

SECRET = "s" * 32
KEY = hp.caller_key(SECRET, "handler:toy-main")
BUSY = {"left": 0}
PROMPTS = []

PKG = {
    "environment.yaml": """environment: toy
work: back-office
sensors:
  asked: {source: {kind: items, type: ask}, starts: true}
actions: {add: free, answer: free, stop: free}
episode: {max_steps: 4}
private: [secret]
model: {agent: m-toy, environment: null}
outcome: {metric: scored.right, floor: {nothing: 0.0, constant: 0.0}, scorer: score.py}
""",
    "agent.yaml": "handlers:\n  main: {kind: model, entry: handlers/model.py}\nparameters: {limit: {value: 2, range: [1, 3]}}\n",
    "environment.py": '''
class Env:
    max_steps = 4
    def actions(self):
        return [{"kind": "add"}, {"kind": "answer"}, {"kind": "stop"}]
    def reset(self, case, seed=0):
        self.case, self.n, self.end = case, 0, None
        return [{"subject": case["id"], "property": k, "value": v, "source": case["id"], "time": None}
                for k, v in case.items() if k not in ("id", "at")]
    def step(self, a):
        if a["kind"] == "add":
            self.n += 1
            return [{"subject": "n", "property": "n", "value": self.n, "source": "env", "time": None}], None, False, False, {}
        self.end = a["kind"]
        return [], None, True, False, {"escalated": a["kind"] == "stop"}
    def final(self):
        return {"answer": self.n if self.end == "answer" else None, "handed_off": self.end == "stop" or None}
class Record:
    def __init__(self, path=None, network=False):
        self.entries, self.new = {}, []
def make(record=None):
    return Env()
''',
    "handlers/model.py": '''
import json, secrets
from ladder import Answer, Escalate, handler
def make(slug, cfg, gateway, directory):
    @handler(slug)
    def main(item, ask):
        cid = secrets.token_hex(6)
        log = [{"role": "user", "content": json.dumps(s["observation"])} for s in item["episode"]] + [
               {"role": "user", "content": json.dumps(item["observation"])}]
        code, r = gateway.chat("handler:" + slug, cfg["model"], log, 50, cid, tools=[{"type": "function", "function": {"name": "add"}}])
        if code != 200:
            return Escalate(f"gateway {code}", meta={"gateway_call": cid})
        call = r["choices"][0]["message"]["tool_calls"][0]["function"]
        return Answer({"kind": call["name"]}, 1.0, meta={"gateway_call": cid, "limit": cfg["parameters"]["limit"]["value"]})
''',
}


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        cid = self.headers.get("x-wb-call")
        if self.headers.get("x-bf-vk") != KEY:
            return self.reply(401, {"error": {"message": "no key"}})
        PROMPTS.append(body)
        if BUSY["left"] > 0:
            BUSY["left"] -= 1
            return self.reply(429, {"error": {"message": "busy"}})
        msgs = [json.loads(m["content"]) for m in body["messages"]]
        first = {c["property"]: c["value"] for c in msgs[0]}
        n = msgs[-1][0]["value"] if len(msgs) > 1 and msgs[-1] else 0
        name = "stop" if first.get("question") == "give up" else "answer" if n >= 2 else "add"
        with psycopg.connect(cli.url(DB), autocommit=True) as c:
            c.execute("insert into logs values (%s, %s, 'success', 500.0, 0.0, 40, 3, 'handler:toy-main')", (json.dumps({"x-wb-call": cid}), body["model"]))
        self.reply(200, {"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [{"id": "x", "function": {"name": name, "arguments": "{}"}}]}}]})

    def reply(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


def q(conn, text, *args):
    return conn.execute(text, args).fetchall()


server = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=server.serve_forever, daemon=True).start()
try:
    with tempfile.TemporaryDirectory() as d:
        for rel, text in PKG.items():
            Path(d, "pkg", rel).parent.mkdir(parents=True, exist_ok=True)
            Path(d, "pkg", rel).write_text(text)
        Path(d, "types", "types").mkdir(parents=True)
        Path(d, "types", "plugin.yaml").write_text("id: asks\nversion: 0.1.0\nrequires: {workbench: \"1\"}\ncontent_types: [types/*.json]\n")
        Path(d, "types", "types", "ask.json").write_text(json.dumps({"title": "Ask", "type": "object", "properties": {
            "question": {"type": "string"}, "secret": {"type": "string"}}}))
        Path(d, "streams.yaml").write_text("streams: {}\n")
        os.environ.update({"WB_HANDLERS_ROOT": d, "WB_HANDLERS_GATEWAY_URL": f"http://127.0.0.1:{server.server_port}",
                           "WB_HANDLERS_GATEWAY_SECRET": SECRET, "WB_HANDLERS_METER_URL": cli.url(DB),
                           "WB_HANDLERS_METER_GRACE_MINUTES": "0"})
        cli.migrate()
        cli.load_plugin(ROOT / "plugins/handlers")
        cli.load_plugin(Path(d, "types"))
        plugins = Plugins().load(ROOT / "plugins")
        with cli.connect() as conn:
            conn.execute("create table logs (metadata text, model text, status text, latency numeric, cost numeric,"
                         " prompt_tokens bigint, completion_tokens bigint, virtual_key_name text)")
            conn.execute("insert into api.ask (slug, title, question, secret) values ('count', 'count', 'count to two', 'hidden'),"
                         " ('quit', 'quit', 'give up', 'hidden')")
        r = run_extractor(cli.connect, plugins, "handlers:declare", {"file": "streams.yaml", "packages": "pkg"})
        check("a package directory is declared as a stream with its agent's handlers", r.get("ok"), r)
        with cli.connect() as conn:
            st = q(conn, "select source, episode from api.stream where slug = 'toy'")
            hs = q(conn, "select slug, kind, entry, config from api.handler where stream = 'toy'")
        check("the stream starts episodes from saved items", st and st[0][0] == {"kind": "items", "type": "ask"} and st[0][1]["dir"] == "pkg", st)
        check("the handler is named for the package, with the environment's model and the agent's parameters",
              hs and hs[0][:3] == ("toy-main", "model", "handlers/model.py") and hs[0][3]["model"] == "m-toy"
              and hs[0][3]["parameters"]["limit"]["value"] == 2, hs)
        r = run_extractor(cli.connect, plugins, "handlers:run", {})
        check("run runs the episodes", r.get("ok") and any("2 episodes run (1 answered, 1 handed off" in m for m in r["log"]), r)
        with cli.connect() as conn:
            ins = {s: (st_, f, e) for s, st_, f, e in q(conn, "select slug, status, final, episode from api.input where stream = 'toy'")}
            calls = q(conn, "select input, kind, metered, cost, reason from api.call where stream = 'toy' order by input, slug")
            dec = q(conn, "select key, subject from wb.decision where kind = 'hand-off' and status = 'open'")
        c = ins.get("toy-count")
        check("a saved item starts an episode that ends with the environment's final state",
              c and c[0] == "resolved" and c[1] == {"answer": 2, "handed_off": None} and c[2]["end"] == "terminated" and c[2]["steps"] == 3, c)
        check("each step's observation and action are kept on the input, as claims",
              c and [s["action"]["kind"] for s in c[2]["log"]] == ["add", "add", "answer"] and c[2]["log"][1]["observation"][0]["property"] == "n", c)
        check("a private field never reaches the model", PROMPTS and not any("hidden" in json.dumps(p) for p in PROMPTS), PROMPTS[:1])
        check("the gateway's tools were offered", all(p.get("tools") for p in PROMPTS), PROMPTS[:1])
        check("every step's call is recorded and metered from the gateway's record",
              len([x for x in calls if x[0] == "toy-count"]) == 3 and all(x[2] is True and x[3].get("tokens_in") == 40 for x in calls), calls)
        g = ins.get("toy-quit")
        check("a hand-off leaves the input open and raises it in the review lane",
              g and g[0] == "open" and g[2]["end"] == "escalated" and dec and dec[0][0] == "hand-off:toy-quit", (g, dec))
        before = len(PROMPTS)
        r = run_extractor(cli.connect, plugins, "handlers:run", {})
        with cli.connect() as conn:
            dec = q(conn, "select key from wb.decision where kind = 'hand-off' and status = 'open'")
        check("a second run runs nothing again, and the hand-off stays open", len(PROMPTS) == before and dec == [("hand-off:toy-quit",)], (len(PROMPTS) - before, dec))
        with cli.connect() as conn:
            conn.execute("insert into api.ask (slug, title, question) values ('later', 'later', 'count to two')")
        BUSY["left"] = 1
        run_extractor(cli.connect, plugins, "handlers:run", {})
        with cli.connect() as conn:
            late = q(conn, "select status, episode->'retry' from api.input where slug = 'toy-later'")
        check("an episode a gateway refusal ended is marked to run again", late == [("open", True)], late)
        run_extractor(cli.connect, plugins, "handlers:run", {})
        with cli.connect() as conn:
            late = q(conn, "select status, final->'answer' from api.input where slug = 'toy-later'")
        check("and the next run runs it again, to an answer", late == [("resolved", 2)], late)
finally:
    server.shutdown()
    with psycopg.connect(cli.url("postgres"), autocommit=True) as conn:
        conn.execute(sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(DB)))

print(f"{sum(checks)}/{len(checks)} checks passed")
sys.exit(0 if all(checks) else 1)
