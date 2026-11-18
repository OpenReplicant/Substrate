"""The store's embedding model (Q120), research skill step 3: every candidate on the same cases from the store.

Cases: each DECISIONS.md row that a store page names (S-n), asked two ways, by the row's bold title and by the
owner's quoted words; the right answers are the pages naming that row. Documents: every page in store.page.
A words-only baseline ranks the same pages by full-text (any of the query's words, ts_rank) as the store's
search does today. One line per candidate and case, then a summary per candidate, in
.state/trials/embedding-model/results.txt. Models are Ollama's, pinned by digest below and checked.

    bin/in-tools python3 scripts/trials/embedding-model/trial.py
"""
import json, math, re, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT)]
from db import connect, DB  # noqa: E402
from gateway import settings  # noqa: E402

OLLAMA = "http://127.0.0.1:11434"
OUT = ROOT / ".state/trials/embedding-model"
K = 5

# name: (Ollama digest prefix, query prefix, document prefix), each from the model's card
CANDIDATES = {
    "qwen3-embedding:0.6b": ("ac6da0dfba84", "Instruct: Given a question, retrieve the parts and decisions it is about\nQuery: ", ""),
    "embeddinggemma-2:270m": ("c21dd30c1e38", "task: search result | query: ", "title: none | text: "),
    "nomic-embed-text:v1.5": ("0a109f422b47", "search_query: ", "search_document: "),
    "snowflake-arctic-embed2:568m": ("5de93a84837d", "query: ", ""),
    "bge-m3:567m": ("790764642607", "", ""),
}


def ollama(path, body=None):
    req = urllib.request.Request(OLLAMA + path, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=600).read())


def embed(model, texts):
    out = []
    for i in range(0, len(texts), 16):
        out += ollama("/api/embed", {"model": model, "input": texts[i:i + 16], "truncate": True})["embeddings"]
    return out


def cases():
    """(decision, kind, query) for each row a page names, with a title and, where there is one, the owner's words."""
    rows = {}
    for line in (ROOT / "DECISIONS.md").read_text().splitlines():
        m = re.match(r"\| (S-\d+) \| \*\*(.+?)\*\*(.*)", line)
        if m:
            rows[m[1]] = (m[2], m[3])
    return rows


def rank_words(c, q):
    words = [w for w in re.findall(r"\w+", q.lower()) if len(w) > 2]
    if not words:
        return []
    tsq = " | ".join(words)
    return [r[0] for r in c.execute(
        "select entity_id from store.page, to_tsquery('simple', %s) q where tsv @@ q "
        "order by ts_rank(tsv, q) desc, entity_id", (tsq,))]


def score(ranked, targets):
    hit = sum(1 for d in ranked[:K] if d in targets) / min(K, len(targets))
    rr = next((1 / (i + 1) for i, d in enumerate(ranked) if d in targets), 0.0)
    return hit, rr


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    have = {m["name"]: m["digest"] for m in ollama("/api/tags")["models"]}
    for name, (digest, *_) in CANDIDATES.items():
        if not have.get(name, "").startswith(digest):
            sys.exit(f"{name}: not pulled at digest {digest} (have {have.get(name)})")

    with connect(settings(), DB) as c:
        pages = c.execute("select entity_id, markdown from store.page order by entity_id").fetchall()
        rows = cases()
        qs = []   # (case id, query, targets)
        for sid, (title, rest) in sorted(rows.items(), key=lambda r: int(r[0][2:])):
            targets = {e for e, md in pages if re.search(rf"\b{sid}\b", md)}
            if not targets:
                continue
            qs.append((f"{sid}/title", title, targets))
            owner = re.search(r'owner[^"“]{0,40}["“](.+?)["”]', rest)
            if owner and len(owner[1]) > 15:
                qs.append((f"{sid}/owner", owner[1], targets))
        words = {cid: rank_words(c, q) for cid, q, _ in qs}

    ids = [e for e, _ in pages]
    lines, summary = [], {}
    per = {"words (full-text)": {cid: score(words[cid], t) for cid, _, t in qs}}
    for name, (_, qp, dp) in CANDIDATES.items():
        embed(name, ["warm up"])
        t0 = time.monotonic()
        dv = embed(name, [dp + md for _, md in pages])
        doc_ms = (time.monotonic() - t0) * 1000 / len(pages)
        qv = embed(name, [qp + q for _, q, _ in qs])
        norm = lambda v: [x / (math.sqrt(sum(y * y for y in v)) or 1) for x in v]  # noqa: E731
        dv = [norm(v) for v in dv]
        res = {}
        for (cid, _, t), v in zip(qs, qv):
            v = norm(v)
            sims = sorted(((sum(a * b for a, b in zip(v, d)), i) for i, d in zip(ids, dv)), reverse=True)
            res[cid] = score([i for _, i in sims], t)
        per[name] = res
        summary[name] = (len(dv[0]), doc_ms)

    base = per["words (full-text)"]
    for name, res in per.items():
        for cid, (hit, rr) in res.items():
            lines.append(f"{name}\t{cid}\trecall@{K} {hit:.2f}\tmrr {rr:.3f}")
    lines.append("")
    lines.append(f"cases: {len(qs)} ({sum(1 for q in qs if q[0].endswith('/title'))} titles, "
                 f"{sum(1 for q in qs if q[0].endswith('/owner'))} owner quotes); documents: {len(pages)} pages")
    for name, res in per.items():
        r = sum(h for h, _ in res.values()) / len(res)
        m = sum(x for _, x in res.values()) / len(res)
        better = sum(1 for cid in res if res[cid][1] > base[cid][1])
        worse = sum(1 for cid in res if res[cid][1] < base[cid][1])
        n = better + worse
        p = min(1.0, 2 * sum(math.comb(n, i) for i in range(min(better, worse) + 1)) / 2 ** n) if n else 1.0
        dim, ms = summary.get(name, ("-", 0))
        lines.append(f"SUMMARY\t{name}\trecall@{K} {r:.3f}\tmrr {m:.3f}\tvs words (mrr): {better} better, "
                     f"{worse} worse, sign p {p:.3f}\tdim {dim}\tms/page {ms:.0f}")
    (OUT / "results.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(l for l in lines if l.startswith("SUMMARY") or l.startswith("cases")))


if __name__ == "__main__":
    main()
