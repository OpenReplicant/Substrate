"""Vectors for recall (BRIEF.md section 6): each live item's text, embedded by one model through an OpenAI-style
endpoint, kept in wb.embedding with a digest of the text and model it was made from.

    python -m workbench embed [--all]          # make the vectors that are missing or stale
    python -m workbench recall "QUERY" [--depth 1] [--no-vectors]

Settings: WORKBENCH_EMBED_URL (the endpoint's base, e.g. http://gateway:8080), WORKBENCH_EMBED_KEY (sent as
x-bf-vk and as a bearer token), WORKBENCH_EMBED_MODEL, and optional WORKBENCH_EMBED_QUERY_PREFIX and
WORKBENCH_EMBED_DOC_PREFIX (some models want an instruction before a query or a document). Without a URL and a
model there are no vectors, and recall is text and graph only.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request

BATCH = 32


def settings() -> dict | None:
    url, model = os.environ.get("WORKBENCH_EMBED_URL"), os.environ.get("WORKBENCH_EMBED_MODEL")
    if not url or not model:
        return None
    return {"url": url.rstrip("/"), "model": model, "key": os.environ.get("WORKBENCH_EMBED_KEY") or "",
            # a settings file cannot hold a newline, so "\\n" in a prefix stands for one
            "query_prefix": os.environ.get("WORKBENCH_EMBED_QUERY_PREFIX", "").replace("\\n", "\n"),
            "doc_prefix": os.environ.get("WORKBENCH_EMBED_DOC_PREFIX", "").replace("\\n", "\n")}


def vectors(cfg: dict, texts: list[str]) -> list[list[float]]:
    body = json.dumps({"model": cfg["model"], "input": texts}).encode()
    headers = {"Content-Type": "application/json"}
    if cfg["key"]:
        headers.update({"x-bf-vk": cfg["key"], "Authorization": f"Bearer {cfg['key']}"})
    req = urllib.request.Request(f"{cfg['url']}/v1/embeddings", body, headers)
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"embeddings endpoint {e.code}: {e.read()[:300]!r}") from None
    return [d["embedding"] for d in sorted(data["data"], key=lambda d: d["index"])]


def literal(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6g}" for x in v) + "]"


def documents(conn) -> list[tuple[str, str, str]]:
    """(type, id, text) for every live item: its title and every text field, as search reads it."""
    out = []
    for (t,) in conn.execute("select id from wb.content_type order by id").fetchall():
        cols = [c for (c,) in conn.execute(
            """select column_name from information_schema.columns
                where table_schema = 'content' and table_name = %s and data_type in ('text', 'jsonb')
                  and column_name not in ('created_by', 'updated_by') order by ordinal_position""", (t,)).fetchall()]
        if not cols:
            continue
        sel = ", ".join(f'"{c}"' for c in cols)
        for row in conn.execute(f'select id, {sel} from api."{t}" x where wb.live(x.id)').fetchall():
            parts = []
            for c, v in zip(cols, row[1:]):
                if v in (None, "", {}, []):
                    continue
                parts.append(f"{c}: {v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)}")
            text = "\n".join(parts)[:6000]
            if text:
                out.append((t, str(row[0]), text))
    return out


def digest(model: str, text: str) -> str:
    return hashlib.sha256(f"{model}\n{text}".encode()).hexdigest()


def embed(conn, cfg: dict, every: bool = False) -> dict:
    """Make the vectors that are missing or stale for cfg's model; drop those of items no longer live."""
    docs = documents(conn)
    have = {(t, i): d for t, i, d in conn.execute(
        "select subject_type, subject_id::text, digest from wb.embedding where model = %s", (cfg["model"],)).fetchall()}
    todo = [(t, i, x) for t, i, x in docs if every or have.get((t, i)) != digest(cfg["model"], x)]
    for n in range(0, len(todo), BATCH):
        chunk = todo[n:n + BATCH]
        vs = vectors(cfg, [cfg["doc_prefix"] + x for _, _, x in chunk])
        for (t, i, x), v in zip(chunk, vs):
            conn.execute("""insert into wb.embedding (subject_type, subject_id, model, embedding, digest)
                            values (%s, %s, %s, %s::vector, %s)
                            on conflict (subject_type, subject_id, model)
                            do update set embedding = excluded.embedding, digest = excluded.digest, created_at = now()""",
                         (t, i, cfg["model"], literal(v), digest(cfg["model"], x)))
    live = {(t, i) for t, i, _ in docs}
    gone = [k for k in have if k not in live]
    for t, i in gone:
        conn.execute("delete from wb.embedding where subject_type = %s and subject_id = %s and model = %s", (t, i, cfg["model"]))
    return {"model": cfg["model"], "items": len(docs), "embedded": len(todo), "dropped": len(gone)}


def query_vector(cfg: dict | None, q: str) -> str | None:
    if not cfg or not q.strip():
        return None
    return literal(vectors(cfg, [cfg["query_prefix"] + q])[0])


def recall(conn, q: str, lim: int = 20, depth: int = 1, use_vectors: bool = True, w_graph: float = 1.0) -> list[dict]:
    cfg = settings() if use_vectors else None
    qv = query_vector(cfg, q)
    rows = conn.execute("select type, id, title, snippet, score, via from api.recall(%s::text, %s::vector, %s::text, %s::integer, %s::integer, %s::real)",
                        (q, qv, cfg["model"] if cfg else None, lim, depth, w_graph)).fetchall()
    return [{"type": r[0], "id": str(r[1]), "title": r[2], "snippet": r[3], "score": round(r[4], 5), "via": r[5]} for r in rows]
