"""The judge's meter (scripts/gateway.py judge-meter, S-87, S-96, S-106) against a fake `logs` table, in a throwaway
database: the columns it reads, typed as Bifrost v2.3.2 makes them. The gateway's marker call is faked: it writes
the marker's row, as the gateway would. The close should:
- count only the judge's key's rows inside the window (after the open, up to the marker), the marker left out
- keep its keys and their meaning: calls, answered, tokens (in plus out), tokens_in, tokens_out, cost
- add tokens_cached, seconds and seconds_upstream (milliseconds in the record, seconds out) and retries, nulls as zero

    WORKBENCH_ADMIN_URL=postgresql://postgres:...@127.0.0.1:5432/postgres python3 scripts/tests/test_gateway.py
"""
import json
import os
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import psycopg  # noqa: E402
from psycopg import sql  # noqa: E402

import gateway  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print(("ok  " if ok else "FAIL"), name, "" if ok else detail)


ADMIN = os.environ["WORKBENCH_ADMIN_URL"]
DB = f"gateway_test_{os.getpid()}"
TEST_URL = ADMIN.rsplit("/", 1)[0] + "/" + DB
TABLE = """create table logs (id text primary key, timestamp timestamptz not null, metadata text, virtual_key_name varchar,
             status varchar, prompt_tokens bigint, completion_tokens bigint, cached_read_tokens bigint default 0,
             latency numeric, upstream_latency numeric, number_of_retries bigint default 0, cost numeric)"""


def row(c, id, at, key=gateway.JUDGE, call=None, status="success", tin=None, tout=None, cached=None, ms=None,
        ms_up=None, retries=None, cost=None):
    c.execute("insert into logs values (%s, to_timestamp(%s), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
              (id, at, json.dumps({"x-wb-call": call}) if call else None, key, status, tin, tout, cached, ms, ms_up,
               retries, cost))


def main():
    with psycopg.connect(ADMIN, autocommit=True) as c:
        c.execute(sql.SQL("create database {}").format(sql.Identifier(DB)))
    real_connect, real_urlopen, real_root = psycopg.connect, urllib.request.urlopen, gateway.ROOT
    try:
        with psycopg.connect(TEST_URL, autocommit=True) as c:
            c.execute(TABLE)
        state = tempfile.mkdtemp()
        gateway.ROOT = Path(state)
        env = {"MORPHOGEN_JUDGE_KEY": "k" * 40, "GATEWAY_METER_PASSWORD": "p", "GATEWAY_PORT": "1"}
        opened = gateway.judge_meter(env, "open", "run-1")
        check("open hands the run the judge's key", opened == {"env": {"WB_GATEWAY_KEY": env["MORPHOGEN_JUDGE_KEY"]}}, opened)
        start = float((Path(state) / ".state/gateway/judge/run-1").read_text())
        at = {"marker": start + 4}

        with psycopg.connect(TEST_URL, autocommit=True) as c:
            row(c, "before", start - 60, tin=999, tout=999, cached=999, ms=99000, retries=9, cost=9)   # before the open
            row(c, "a", start + 1, call="c1", tin=700, tout=40, cached=650, ms=812.5, ms_up=811.25, cost=0.002)
            row(c, "b", start + 2, call="c2", tin=769, tout=31, cached=704, ms=590.25, ms_up=589.5, retries=2)
            row(c, "c", start + 3, status="error", ms=1200.0, ms_up=None, retries=1)   # turned away: no tokens, no cost
            row(c, "other", start + 2, key="handler:someone", tin=500, tout=500, cached=500, ms=5000, retries=5, cost=5)
            row(c, "after", start + 3600, tin=999, tout=999, cached=999, ms=99000, retries=9, cost=9)   # after the marker

        def fake_urlopen(req, timeout=None):
            # the gateway records the marker call (an embedding: tokens and time of its own, which must not count)
            marker = req.headers.get("X-wb-call")
            with real_connect(TEST_URL, autocommit=True) as c:
                row(c, "marker", at["marker"], call=marker, tin=1, tout=0, ms=30.0, ms_up=29.0)

            class R:
                def read(self):
                    return b"{}"
            return R()

        psycopg.connect = lambda url, **kw: real_connect(TEST_URL, **kw)
        urllib.request.urlopen = fake_urlopen
        t = time.time()
        got = gateway.judge_meter(env, "close", "run-1")
        took = time.time() - t

        old = {"calls": 3, "answered": 2, "tokens": 1540, "tokens_in": 1469, "tokens_out": 71, "cost": 0.002}
        check("the old keys keep their meaning", {k: got.get(k) for k in old} == old, got)
        check("tokens is still tokens in plus out", got["tokens"] == got["tokens_in"] + got["tokens_out"], got)
        check("cached input tokens are summed over the window, nulls as zero", got.get("tokens_cached") == 1354, got)
        check("latency is in seconds, from Bifrost's milliseconds",
              abs(got.get("seconds", -1) - 2.60275) < 1e-9, got.get("seconds"))
        check("upstream latency is in seconds, an unmeasured call as zero",
              abs(got.get("seconds_upstream", -1) - 1.40075) < 1e-9, got.get("seconds_upstream"))
        check("retries are summed", got.get("retries") == 3, got)
        check("every value is a plain number (Morphogen takes only numbers as metered.<key>)",
              all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in got.values()), got)
        check("exactly the keys of cell.md rule 3", set(got) == set(old) | {"tokens_cached", "seconds", "seconds_upstream", "retries"}, sorted(got))
        check("the run's state is cleared", not (Path(state) / ".state/gateway/judge/run-1").exists())
        check("it closed without waiting out the window", took < 10, took)

        with real_connect(TEST_URL, autocommit=True) as c:
            c.execute("truncate logs")
        gateway.judge_meter(env, "open", "run-2")
        at["marker"] = float((Path(state) / ".state/gateway/judge/run-2").read_text()) + 1
        empty = gateway.judge_meter(env, "close", "run-2")
        check("a run with no calls counts zeros, not nulls",
              empty == {"calls": 0, "answered": 0, "tokens": 0, "tokens_in": 0, "tokens_out": 0, "cost": 0.0,
                        "tokens_cached": 0, "seconds": 0.0, "seconds_upstream": 0.0, "retries": 0}, empty)
    finally:
        psycopg.connect, urllib.request.urlopen, gateway.ROOT = real_connect, real_urlopen, real_root
        with psycopg.connect(ADMIN, autocommit=True) as c:
            c.execute(sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(DB)))
    print(f"{sum(checks)}/{len(checks)} checks passed")
    sys.exit(0 if all(checks) else 1)


if __name__ == "__main__":
    main()
