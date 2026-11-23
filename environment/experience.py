"""The assistant's experience (S-182): one episode per model call the gate sees, the rows System 1 is distilled from.
The Python side of environment/sql/008_experience.sql.

    x = Experience(conn)                       # the key from EXPERIENCE_KEY (.env), or Experience(conn, key)
    ref = x.record("worker:loop", request=messages, responder="slow", response=text, features={...},
                   embedding=vec, embedder="ollama/qwen3-embedding:0.6b", decision={...}, impasse="low")
    x.outcome(ref, "ok", True, source="task")  # later, by the ref: ok (bool), correct (a responder), score (0..1)
    x.episodes(caller="worker:loop")           # the decider's context: features, embedding, latest labels; no text
    x.text(ref)                                # the owner's: the request and response back
    x.forget(ref=...) / x.forget(start=..., end=...) / x.forget(everything=True); x.expire()   # the owner's

The text is encrypted by Postgres (pgcrypto) under the key, passed as a bound parameter and never stored.
"""
from __future__ import annotations

import json
import os
from datetime import datetime

from psycopg.types.json import Jsonb

KINDS = ("ok", "correct", "score")
IMPASSES = ("none", "tie", "low")


def _vector(v) -> str | None:
    return None if v is None else "[" + ",".join(repr(float(x)) for x in v) + "]"


class Experience:
    def __init__(self, conn, key: str | None = None):
        self.c = conn
        self.key = key if key is not None else os.environ.get("EXPERIENCE_KEY", "")

    def _need_key(self) -> str:
        if not self.key:
            raise ValueError("experience needs EXPERIENCE_KEY (.env; deploy/secrets.txt)")
        return self.key

    def record(self, caller: str, request, responder: str, response: str | None = None, features: dict | None = None,
               embedding=None, embedder: str | None = None, depended_on: list | None = None,
               decision: dict | None = None, impasse: str | None = None) -> str:
        """One episode; returns its ref (a uuid as text). `request` is the call's messages (any JSON) or text."""
        if impasse is not None and impasse not in IMPASSES:
            raise ValueError(f"impasse is one of {IMPASSES}, or None")
        text = request if isinstance(request, str) else json.dumps(request, ensure_ascii=False)
        row = self.c.execute(
            "select env.record_episode(%s, %s, %s, %s, %s, %s::vector, %s, %s, %s, %s, %s)",
            (self._need_key(), caller, text, Jsonb(features or {}), embedder, _vector(embedding), responder, response,
             Jsonb(depended_on or []), Jsonb(decision or {}), impasse)).fetchone()
        return str(row[0])

    def outcome(self, ref: str, kind: str, value, source: str, note: str | None = None) -> int:
        """How an episode turned out, at any time after it (long-horizon feedback)."""
        if kind not in KINDS:
            raise ValueError(f"kind is one of {KINDS}")
        return self.c.execute("select env.add_outcome(%s, %s, %s, %s, %s, %s)",
                              (ref, kind, Jsonb(value), source, note, self.key if note else None)).fetchone()[0]

    def episodes(self, caller: str | None = None, since: datetime | None = None, limit: int = 5000) -> list[dict]:
        """Newest first, with the latest outcome of each kind; no text."""
        rows = self.c.execute("select ref, at, caller, features, embedder, embedding::text, responder, decision, impasse, "
                              "ok, correct, score, outcomes from env.episodes(%s, %s, %s)", (caller, since, limit)).fetchall()
        keys = ("ref", "at", "caller", "features", "embedder", "embedding", "responder", "decision", "impasse",
                "ok", "correct", "score", "outcomes")
        out = []
        for r in rows:
            d = dict(zip(keys, r))
            d["ref"] = str(d["ref"])
            d["embedding"] = None if d["embedding"] is None else json.loads(d["embedding"])
            d["score"] = None if d["score"] is None else float(d["score"])
            out.append(d)
        return out

    # ---- the owner's (granted to no login; run as the owner)

    def text(self, ref: str) -> dict | None:
        row = self.c.execute("select request, response from env.episode_text(%s, %s)", (ref, self._need_key())).fetchone()
        return None if row is None else {"request": row[0], "response": row[1]}

    def forget(self, ref: str | None = None, start: datetime | None = None, end: datetime | None = None,
               everything: bool = False) -> int:
        """Delete one episode, those in [start, end), or all; their outcomes with them. Returns how many episodes."""
        return self.c.execute("select env.forget_experience(%s, %s, %s, %s)", (ref, start, end, everything)).fetchone()[0]

    def expire(self) -> int:
        """Delete what is older than the retention (select env.set('experience', 'retention_days', '30', 'owner'))."""
        return self.c.execute("select env.expire_experience()").fetchone()[0]
