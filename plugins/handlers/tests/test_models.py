"""Model handlers through a gateway (README.md, "Model handlers"), in a throwaway database. A fake gateway in this
process answers like an OpenAI-style endpoint and keeps its own log table, as the real one does; the meter reads
that table. The run should:
- answer through the gateway, with the cost the gateway recorded, not the handler's own timing
- escalate when the model is not sure, or its reply cannot be read
- refuse a call the gateway has no record of, once the grace period is over
- refuse a call the gateway records under another caller's key
- ask a handler that joined the stream later on inputs already seen
- never show the model the outcome

    WORKBENCH_ADMIN_URL=postgresql://postgres:...@127.0.0.1:5432/postgres python3 plugins/handlers/tests/test_models.py
"""
import json
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "workbench"), str(ROOT / "plugins/handlers")]
os.environ["WORKBENCH_DB"] = DB = f"workbench_test_{os.getpid()}"
os.environ.setdefault("WORKBENCH_JWT_SECRET", "m-" + "z" * 40)

import psycopg  # noqa: E402
from psycopg import sql  # noqa: E402

from workbench import cli  # noqa: E402
from workbench.extract import Plugins, run_extractor  # noqa: E402
import handlers_plugin as hp  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print(("ok  " if ok else "FAIL"), name, "" if ok else detail)


SECRET = "s" * 32
CALLERS = {hp.caller_key(SECRET, f"handler:{h}"): f"handler:{h}" for h in ("sure", "unsure", "garbled", "ghost", "borrower", "late", "flaky", "loose")}
BUSY = {"left": 2}    # the flaky model's provider refuses its first two calls (one per input), then answers
SEEN = []          # what the models were shown


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        key, cid = self.headers.get("x-bf-vk"), self.headers.get("x-wb-call")
        caller = CALLERS.get(key)
        if not caller:
            return self.reply(401, {"error": {"message": "no key"}})
        SEEN.append(body["messages"][-1]["content"])
        model = body["model"]
        if model == "m-flaky" and BUSY["left"] > 0:
            BUSY["left"] -= 1
            with psycopg.connect(cli.url(DB), autocommit=True) as c:
                c.execute("insert into logs values (%s, %s, 'error', 80.0, 0, 0, 0, %s)", (json.dumps({"x-wb-call": cid}), model, caller))
            return self.reply(429, {"error": {"message": "rate-limited upstream"}})
        if model == "m-flaky":
            model = "m-sure"
        text = {"m-sure": '{"answer": "declined", "confidence": 0.9, "reason": "like the others"}',
                "m-unsure": 'Here: {"answer": "declined", "confidence": 0.3, "reason": "hard to say"}',
                "m-garbled": "I think it should probably be declined.",
                "m-loose": '{"answer": "declined", "confidence": 0.85, "reason": like the others}',
                "m-ghost": '{"answer": "declined", "confidence": 0.95, "reason": "x"}'}.get(model, "{}")
        if model != "m-ghost":   # the ghost answers, but the gateway keeps no record of it
            as_caller = "handler:sure" if model == "m-borrow" else caller
            if model == "m-borrow":
                text = '{"answer": "approved", "confidence": 0.99, "reason": "y"}'
            with psycopg.connect(cli.url(DB), autocommit=True) as c:
                c.execute("insert into logs values (%s, %s, 'success', 1234.0, 0.0002, 11, 5, %s)",
                          (json.dumps({"x-wb-call": cid}), model, as_caller))
        self.reply(200, {"choices": [{"message": {"role": "assistant", "content": text}}], "usage": {"prompt_tokens": 11}})

    def reply(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


STREAMS = """streams:
  gaps:
    description: a drift checker's gaps; approve one to change the map, decline it to keep the map
    source: {kind: decisions, raised_by: "x:drift", decision_kind: gap}
    answers: advisory
    handlers:
      sure: {kind: model, entry: model, model: m-sure, answers: [approved, declined], sure_at: 0.8}
      unsure: {kind: model, entry: model, model: m-unsure, answers: [approved, declined], sure_at: 0.8}
      garbled: {kind: model, entry: model, model: m-garbled, answers: [approved, declined]}
      ghost: {kind: model, entry: model, model: m-ghost, answers: [approved, declined]}
      borrower: {kind: model, entry: model, model: m-borrow, answers: [approved, declined]}
      flaky: {kind: model, entry: model, model: m-flaky, answers: [approved, declined]}
      loose: {kind: model, entry: model, model: m-loose, answers: [approved, declined]}
      review-lane: {kind: person}
"""


def q(conn, text, *args):
    return conn.execute(text, args).fetchall()


server = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=server.serve_forever, daemon=True).start()
try:
    with tempfile.TemporaryDirectory() as d:
        Path(d, "streams.yaml").write_text(STREAMS)
        os.environ.update({"WB_HANDLERS_ROOT": d, "WB_HANDLERS_GATEWAY_URL": f"http://127.0.0.1:{server.server_port}",
                           "WB_HANDLERS_GATEWAY_SECRET": SECRET, "WB_HANDLERS_METER_URL": cli.url(DB),
                           "WB_HANDLERS_METER_GRACE_MINUTES": "0"})
        cli.migrate()
        cli.load_plugin(ROOT / "plugins/handlers")
        plugins = Plugins().load(ROOT / "plugins")
        with cli.connect() as conn:
            conn.execute("create table logs (metadata text, model text, status text, latency numeric, cost numeric,"
                         " prompt_tokens bigint, completion_tokens bigint, virtual_key_name text)")
            for key, status, by in (("undeclared:volume:a", "declined", "owner"), ("undeclared:volume:b", "open", None)):
                conn.execute("""insert into wb.decision (kind, key, raised_by, subject, status, decided_by, decided_at, created_at)
                                values ('gap', %s, 'x:drift', '{}', %s, %s, case when %s::text is null then null else now() end,
                                        now() - interval '1 hour')""", (key, status, by, by))
        r = run_extractor(cli.connect, plugins, "handlers:declare", {"file": "streams.yaml"})
        check("declare runs", r.get("ok"), r)
        r = run_extractor(cli.connect, plugins, "handlers:run", {})
        check("run runs", r.get("ok"), r)
        with cli.connect() as conn:
            calls = {f"{h} {k.split(':')[-1]}": (kind, val, conf, cost, metered, reason)
                     for h, k, kind, val, conf, cost, metered, reason in q(conn, """select c.handler, i.key, c.kind, c.value, c.confidence,
                        c.cost, c.metered, c.reason from api.call c join api.input i on i.slug = c.input""")}
        a = calls.get("sure a")
        check("a sure model answers through the gateway", a and a[:3] == ("answer", "declined", 0.9), a)
        check("its cost is the gateway's record: money, time and tokens, not its own timing",
              a and a[4] is True and a[3] == {"person": 0, "usd": 0.0002, "seconds": 1.234, "tokens_in": 11, "tokens_out": 5}, a)
        u = calls.get("unsure a")
        check("an unsure model escalates, saying why", u and u[0] == "escalate" and "not sure" in u[5], u)
        g = calls.get("garbled a")
        check("a reply with no answer in it escalates", g and g[0] == "escalate" and "no answer" in g[5], g)
        h = calls.get("ghost a")
        check("a call the gateway has no record of is refused once the grace is over", h and h[0] == "refused" and "no record" in h[5], h)
        b = calls.get("borrower a")
        check("a call the gateway records under another caller is refused", b and b[0] == "refused" and "handler:sure" in b[5], b)
        check("the models never saw the outcome", SEEN and not any("owner" in s for s in SEEN), SEEN[:1])
        check("the models saw the earlier decisions", any("earlier decisions" in s for s in SEEN), SEEN[:1])
        lo = calls.get("loose a")
        check("an almost-JSON reply (an unquoted reason) is still read", lo and lo[:3] == ("answer", "declined", 0.85), lo)
        f = calls.get("flaky a")
        check("a call the gateway turns away escalates with the gateway's reason", f and f[0] == "escalate" and f[5].startswith("gateway 429"), f)
        with cli.connect() as conn:
            scored = q(conn, "select correct from api.call where handler = 'sure' and input like '%%volume-a%%'")
        check("a model's answer is scored against the person's decision", scored == [(True,)], scored)

        Path(d, "streams.yaml").write_text(STREAMS + "      late: {kind: model, entry: model, model: m-sure, answers: [approved, declined]}\n")
        run_extractor(cli.connect, plugins, "handlers:declare", {"file": "streams.yaml"})
        before = len(SEEN)
        r = run_extractor(cli.connect, plugins, "handlers:run", {})
        with cli.connect() as conn:
            late = q(conn, "select count(*) from api.call where handler = 'late' and metered")[0][0]
            again = q(conn, "select count(*) from api.call where handler = 'sure'")[0][0]
            flaky = q(conn, "select kind, value from api.call where handler = 'flaky' order by input")
        check("a handler that joins later is asked on the inputs already seen", late == 2, (late, r))
        check("a call the gateway turned away is made again, and now answers", flaky == [("answer", "declined")] * 2, flaky)
        check("and the others are not asked again", again == 2 and len(SEEN) - before == 4, (again, len(SEEN) - before))
finally:
    server.shutdown()
    with psycopg.connect(cli.url("postgres"), autocommit=True) as conn:
        conn.execute(sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(DB)))

print(f"{sum(checks)}/{len(checks)} checks passed")
sys.exit(0 if all(checks) else 1)
