"""The real-time environment (plan step 3c): signals, subscribers, actuators and gates on pgmq, in the store's
database (schema `env`, store/sql/005_environment.sql). This module is the Python side of those functions; the
channel into Claude Code is environment.channel.
"""
from __future__ import annotations

import json

from psycopg.types.json import Jsonb


class Env:
    def __init__(self, conn):
        self.c = conn

    def publish(self, key: str, body, by: str, headers: dict | None = None) -> int:
        return self.c.execute("select env.publish(%s, %s, %s, %s)", (key, Jsonb(body), by, Jsonb(headers or {}))).fetchone()[0]

    def subscribe(self, queue: str, patterns: list[str]) -> None:
        self.c.execute("select env.subscribe(%s, %s)", (queue, patterns))

    def read(self, queue: str, vt: int = 300, qty: int = 10) -> list[dict]:
        """Messages now visible on a queue, hidden from the next read for vt seconds unless acknowledged."""
        rows = self.c.execute("select msg_id, read_ct, message from env.read(%s, %s, %s)", (queue, vt, qty)).fetchall()
        return [{"msg_id": m, "read_ct": n, **(msg if isinstance(msg, dict) else json.loads(msg))} for m, n, msg in rows]

    def ack(self, queue: str, msg_ids: list[int]) -> list[int]:
        return [r[0] for r in self.c.execute("select env.ack(%s, %s::bigint[])", (queue, msg_ids)).fetchall()]

    def actuator(self, name: str, gate: str, by: str, description: str | None = None) -> str:
        return self.c.execute("select env.actuator(%s, %s, %s, %s)", (name, gate, by, description)).fetchone()[0]

    def act(self, actuator: str, input_, by: str) -> tuple[int, str]:
        return tuple(self.c.execute("select * from env.act(%s, %s, %s)", (actuator, Jsonb(input_), by)).fetchone())

    def status(self, action: int) -> str | None:
        r = self.c.execute("select status from env.action where id = %s", (action,)).fetchone()
        return r[0] if r else None

    def decide(self, action: int, approve: bool, person: str, reason: str | None = None) -> str:
        return self.c.execute("select env.decide(%s, %s, %s, %s)", (action, approve, person, reason)).fetchone()[0]

    def done(self, action: int, result, ok: bool = True) -> None:
        self.c.execute("select env.done(%s, %s, %s)", (action, Jsonb(result), ok))

    def waiting(self) -> list[dict]:
        cur = self.c.execute("select id, actuator, input, caller, at from env.action where status = 'proposed' order by id")
        return [dict(zip([d.name for d in cur.description], r)) for r in cur.fetchall()]
