#!/usr/bin/env python3
"""Spec step 24's trial: which parts of recall earn their place, and which embedding model (docs/choices).

For each embedding model, every live item is embedded through the gateway (key workbench:embed, local models
only); then the queries from queries.py are asked of api.recall with its parts switched on in turn:
    text                 words only (what search did before)
    text+vectors         and the nearest items by meaning
    text+vectors+graph   and items a relation or two from the best of those
Parameters (graph depth, its weight) are chosen on the search set only; the held-out set is read once per arm,
with the chosen parameters. Recall at 10 and reciprocal rank per query; each addition is compared, query by
query, with the arm without it: wins, losses, a sign test, and a bootstrap 95% interval of the mean gain.
An A/A pair (the text arm asked twice) shows the noise floor: recall is deterministic, so it must be zero.

    bin/in-tools python3 scripts/trials/recall/run.py MODEL...    # e.g. ollama/qwen3-embedding:0.6b
"""
from __future__ import annotations

import json
import math
import os
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "workbench"), str(ROOT / "scripts")]

from workbench import embed  # noqa: E402

PREFIX = {   # what each model's card asks for before a query and a document
    "qwen3-embedding": ("Instruct: Given a request or question about a software system, retrieve the parts of the "
                        "system it concerns\nQuery: ", ""),
    "nomic-embed-text": ("search_query: ", "search_document: "),
}


def metrics(hits: list[tuple[str, str]], relevant: list[list[str]]) -> tuple[float, float]:
    rel = {tuple(r) for r in relevant}
    top = hits[:10]
    rec = len([h for h in top if h in rel]) / len(rel)
    rr = next((1 / (i + 1) for i, h in enumerate(hits) if h in rel), 0.0)
    return rec, rr


def ask(conn, q, qvec, model, depth, w):
    rows = conn.execute("select type, id from api.recall(%s::text, %s::vector, %s::text, 50, %s::integer, %s::real)", (q, qvec, model, depth, w)).fetchall()
    return [(t, str(i)) for t, i in rows]


def compare(a: list[float], b: list[float]) -> dict:
    d = [y - x for x, y in zip(a, b)]
    wins, losses = sum(x > 0 for x in d), sum(x < 0 for x in d)
    n = wins + losses
    p = 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, k) for k in range(0, min(wins, losses) + 1)) / 2 ** n)
    rnd = random.Random(7)
    boots = sorted(sum(rnd.choice(d) for _ in d) / len(d) for _ in range(4000)) if d else [0]
    return {"mean_gain": round(sum(d) / max(len(d), 1), 4), "wins": wins, "losses": losses, "ties": len(d) - n,
            "sign_p": round(p, 4), "ci95": [round(boots[100], 4), round(boots[3899], 4)]}


def main() -> None:
    import psycopg
    models = sys.argv[1:] or sys.exit(__doc__)
    queries = json.loads((ROOT / ".state/trials/recall/queries.json").read_text())
    url = os.environ["RECALL_DB"]
    out = {"queries": {s: sum(q["split"] == s for q in queries) for s in ("search", "held-out")}, "models": {}}
    with psycopg.connect(url, autocommit=True) as conn:
        base = {}
        for split in ("search", "held-out"):
            base[split] = [metrics(ask(conn, q["query"], None, None, 0, 0), q["relevant"]) for q in queries if q["split"] == split]
        again = [metrics(ask(conn, q["query"], None, None, 0, 0), q["relevant"]) for q in queries if q["split"] == "held-out"]
        out["a_a"] = compare([r for r, _ in base["held-out"]], [r for r, _ in again])
        out["text"] = {s: {"recall10": round(sum(r for r, _ in v) / len(v), 4), "mrr": round(sum(x for _, x in v) / len(v), 4)}
                       for s, v in base.items()}
        for m in models:
            family = next((k for k in PREFIX if k in m), None)
            qp, dp = PREFIX.get(family, ("", ""))
            cfg = {"url": os.environ["WORKBENCH_EMBED_URL"], "model": m, "key": os.environ["WORKBENCH_EMBED_KEY"],
                   "query_prefix": qp, "doc_prefix": dp}
            t0 = time.time()
            made = embed.embed(conn, cfg)
            res = {"embedded": made, "seconds_to_embed": round(time.time() - t0, 1)}
            qv = {}
            for n in range(0, len(queries), 32):
                chunk = queries[n:n + 32]
                for q, v in zip(chunk, embed.vectors(cfg, [qp + q["query"] for q in chunk])):
                    qv[q["id"]] = embed.literal(v)
            # tune the graph on the search set only
            grid = [(d, w) for d in (1, 2) for w in (0.5, 1.0)]
            def score(split, depth, w, use_vec=True):
                return [metrics(ask(conn, q["query"], qv[q["id"]] if use_vec else None, m, depth, w), q["relevant"])
                        for q in queries if q["split"] == split]
            tuned = max(grid, key=lambda dw: sum(r for r, _ in score("search", *dw)))
            res["graph_chosen_on_search"] = {"depth": tuned[0], "weight": tuned[1]}
            held = {"text": base["held-out"], "text+vectors": score("held-out", 0, 0), "text+vectors+graph": score("held-out", *tuned),
                    "text+graph": score("held-out", tuned[0], tuned[1], use_vec=False)}
            res["held_out"] = {k: {"recall10": round(sum(r for r, _ in v) / len(v), 4), "mrr": round(sum(x for _, x in v) / len(v), 4)}
                               for k, v in held.items()}
            res["vectors_vs_text"] = compare([r for r, _ in held["text"]], [r for r, _ in held["text+vectors"]])
            res["graph_vs_text+vectors"] = compare([r for r, _ in held["text+vectors"]], [r for r, _ in held["text+vectors+graph"]])
            res["graph_vs_text"] = compare([r for r, _ in held["text"]], [r for r, _ in held["text+graph"]])
            out["models"][m] = res
            print(json.dumps({m: res}, indent=1))
    path = ROOT / ".state/trials/recall/results.json"
    path.write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "models"}, indent=1))


if __name__ == "__main__":
    main()
