"""The paper catalog's extractors (docs/tasks/paper-catalog.md, leg one; no model anywhere):

  papers:listings   each listing in listings.yaml: a GitHub list's arXiv identifiers, the headings they sat under and
                    their lines, or a saved arXiv search's results; the papers they name, each listed in them
  papers:metadata   each paper's title, authors, abstract and the rest from arXiv's API, 100 identifiers a request,
                    one request every three seconds, most-listed first (input batches, default 80 requests)
  papers:testable   each paper with a repository, by rule: GitHub reports a permissive or LGPL licence and it is not
                    archived; most-listed first, up to `checks` repositories a run (default 100) or what GitHub's rate
                    limit allows, resuming where it stopped
  papers:citations  each paper's OpenAlex id, citation count and venue (the DOI 10.48550/arXiv.ID, 100 to a call, most-listed
                    first, up to `calls` list calls a run, default 200; a paper checked in the last 30 days is not asked
                    again); skipped, saying so, when no OpenAlex key is set (WB_PAPERS_OPENALEX_KEY, from OPENALEX_API)
  papers:harvest    listings, metadata, citations, testable in order

Inputs for all: listings (a file, default packages/papers/listings.yaml), replay (a directory of recorded fetches: no
network), state (where fetches are recorded, default .state/papers), max_age_hours (default 1).

A value's claim quotes the Atom element, the JSON key or the link it was read from, and its source is that URL. From a
list only the arXiv identifier, the heading path and the line are taken: the keeper's descriptions are not copied.
GitHub is read without a login (60 requests an hour) unless WB_PAPERS_GITHUB_TOKEN is set in the extractor's environment
(scripts/workbench.sh passes it from PAPERS_GITHUB_TOKEN). The OpenAlex key goes only in an Authorization header.
"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

import yaml

from papers_lib import (ARXIV_API, Fetcher, default_token, find_repositories, parse_atom, parse_list, read_repo, rule,
                        slug_for)

PACKAGE = Path(__file__).resolve().parent.parent


def norm(v):
    return json.dumps(v, sort_keys=True, default=str)


def query_url(q: dict) -> str:
    return (f"{ARXIV_API}?search_query={quote(q['search_query'], safe=':')}&start=0&max_results={int(q.get('max_results', 300))}"
            "&sortBy=relevance&sortOrder=descending")


def listing_slug(spec: dict) -> str:
    return "arxiv-query-" + spec["name"] if "name" in spec else spec["repository"].lower().replace("/", "-")


def line_of(text: str, needle: str) -> dict | None:
    for n, line in enumerate(text.splitlines(), 1):
        if needle in line:
            return {"quote": line.strip(), "span": {"start_line": n, "end_line": n}}
    return None


def key_quote(key: str, value, pointer: str) -> dict:
    return {"quote": f"{json.dumps(key)}: {json.dumps(value)}", "span": {"pointer": pointer}}


class Writer:
    """Writes an item only when a value changed and says whether it did. The source is read lazily, so an unchanged
    item costs nothing and a second run over unchanged sources writes nothing."""

    def __init__(self, ctx, type_id):
        self.ctx, self.type = ctx, type_id
        self.have = {r[0]["slug"]: r[0] for r in ctx.conn.execute(f"select to_jsonb(x) from api.{type_id} x").fetchall()}
        self.created, self.changed = set(), set()

    def put(self, slug, fields, title, source, evidence=None):
        now = self.have.get(slug)
        fields = {k: v for k, v in fields.items() if v is not None}
        want = {**fields, "title": title}
        if now and all(norm(now.get(k)) == norm(v) for k, v in want.items()):
            return now["id"], False
        item = self.ctx.upsert(self.type, slug, fields, title=title, source=source() if callable(source) else source,
                               evidence=evidence or {})
        if now is None:
            self.created.add(slug)
        self.changed.add(slug)
        self.have[slug] = {**(now or {}), "id": item, "slug": slug, **want}
        return item, True


class Harvest:
    def __init__(self, ctx, inputs, root):
        self.ctx, self.inputs = ctx, inputs
        f = Path(inputs.get("listings") or PACKAGE / "listings.yaml")
        self.file = f if f.is_absolute() else root / f
        self.data = self.file.read_bytes()
        self.spec = yaml.safe_load(self.data) or {}
        state = Path(inputs["state"]) if inputs.get("state") else root / ".state" / "papers"
        self.fetcher = Fetcher(state, replay=Path(inputs["replay"]) if inputs.get("replay") else None,
                               max_age=float(inputs.get("max_age_hours", 1)) * 3600, token=default_token(),
                               openalex_key=os.environ.get("WB_PAPERS_OPENALEX_KEY") or None)
        self.listings, self.papers = Writer(ctx, "listing"), Writer(ctx, "paper")
        self.stats = {"listings": 0, "papers_new": 0, "listed_in": 0, "metadata": 0, "not_found": 0, "cited": 0, "checked": 0, "testable": 0}
        self._sources = {}
        try:
            self.file_name = str(self.file.relative_to(root))
        except ValueError:
            self.file_name = self.file.name

    # a source, once however many values cite it
    def source(self, uri, data, media):
        key = (uri, len(data))
        if key not in self._sources:
            self._sources[key] = self.ctx.source(uri, data, media)
        return self._sources[key]

    def of(self, reply, media="text/plain"):
        return lambda: self.source(reply.url, reply.body, media)

    def file_source(self):
        return self.source("file:" + self.file_name, self.data, "application/yaml")

    # ---------------------------------------------------------------- pass 1: listings

    def read(self):
        """Every listing's sources, fetched: [{kind, spec, slug, title, entries, unresolved, replies, missed, api, atom}]."""
        out = []
        for s in self.spec.get("lists") or []:
            repo = s["repository"]
            L = {"kind": "list", "spec": s, "slug": listing_slug(s), "title": repo, "entries": [], "replies": [], "missed": False,
                 "api": self.fetcher.get(f"https://api.github.com/repos/{repo}", max_age=86400), "unresolved": set()}
            for name in s.get("files") or ["README.md"]:
                raw_url = f"https://raw.githubusercontent.com/{repo}/HEAD/{name}"
                r = self.fetcher.get(raw_url)
                if r is None or not r.ok:
                    L["missed"] = True
                    continue
                if r.stale:
                    self.ctx.log(f"{repo} {name}: not readable now; the recording of {r.read_at[:10]} is used")
                es, other = parse_list(r.text())
                for e in es:
                    e.update(url=f"https://github.com/{repo}/blob/HEAD/{name}#L{e['line']}", raw=raw_url)
                L["entries"] += es
                L["unresolved"] |= set(other)
                L["replies"].append(r)
            out.append(L)
        for q in self.spec.get("queries") or []:
            url = query_url(q)
            r = self.fetcher.get(url)
            recs = parse_atom(r.text()) if r and r.ok else []
            es = [{"id": rec["arxiv_id"], "heading": q["topic"], "line": n, "link": url, "url": f"{url}#result-{n}", "raw": url}
                  for n, rec in enumerate(recs, 1)]
            out.append({"kind": "query", "spec": q, "slug": listing_slug(q), "title": "arXiv search: " + q["name"], "entries": es,
                        "unresolved": set(), "replies": [r] if r and r.ok else [], "missed": not (r and r.ok), "api": None,
                        "atom": recs, "url": url})
        return out

    def listings_pass(self):
        ctx, lw, pw, st = self.ctx, self.listings, self.papers, self.stats
        text = self.data.decode()
        found = self.read()
        ids = {}
        for L in found:
            s, api, first = L["spec"], L["api"], (L["replies"] or [None])[0]
            title = L["title"]
            if L["kind"] == "list":
                declared = {"kind": "list", "repository": s["repository"], "url": f"https://github.com/{s['repository']}",
                            "topic": s.get("topic"), "machine_built": bool(s.get("machine_built"))}
                at = line_of(text, f"repository: {s['repository']}")
                github, gev = {}, {}
                if api and api.ok:
                    d = json.loads(api.body)
                    spdx = (d.get("license") or {}).get("spdx_id")
                    github = {"licence": spdx or "none reported", "last_changed": (d.get("pushed_at") or "")[:10] or None,
                              "stars": d.get("stargazers_count")}
                    gev = {"licence": key_quote("spdx_id", spdx, "/license/spdx_id"),
                           "last_changed": key_quote("pushed_at", d.get("pushed_at"), "/pushed_at"),
                           "stars": key_quote("stargazers_count", d.get("stargazers_count"), "/stargazers_count")}
                    lw.put(L["slug"], github, title, self.of(api, "application/json"), gev)
                else:
                    ctx.log(f"{s['repository']}: GitHub did not answer (its rate limit?); licence, stars and last push keep their earlier values")
                counted = {}
            else:
                recs = L["atom"]
                newest = max((r.get("updated", "") for r in recs), default="") or None
                declared = {"kind": "query", "url": L["url"], "topic": s["topic"], "licence": "CC0-1.0 (arXiv metadata)",
                            "machine_built": False}
                at = line_of(text, f"name: {s['name']}")
                counted = {"last_changed": newest} if newest else {}
            lw.put(L["slug"], declared, title, self.file_source, {k: at for k in declared} if at else {})
            if not L["missed"] and first is not None:
                n = len({e["id"] for e in L["entries"]})
                what = "arXiv identifiers in links" if L["kind"] == "list" else "results of the saved search"
                counted.update(entries=n, unresolved=len(L["unresolved"]))
                cev = {"entries": {"quote": f"{n} {what}", "span": {"pointer": "counted from the page"}},
                       "unresolved": {"quote": f"{len(L['unresolved'])} links to papers without an arXiv identifier",
                                      "span": {"pointer": "counted from the page"}}}
                if L["kind"] == "query" and newest:
                    cev["last_changed"] = {"quote": f"<updated>{newest}</updated> of the newest result", "span": {"pointer": "results"}}
                lw.put(L["slug"], counted, title, self.of(first), cev)
            else:
                ctx.log(f"{L['slug']}: its page could not be read; its earlier counts and entries stand")
            ids[L["slug"]] = lw.have[L["slug"]]["id"]
        st["listings"] = len(lw.changed)

        by_paper = {}
        for L in found:
            if L["missed"] and not L["entries"]:      # not read: what its earlier entries said stands
                for p in pw.have.values():
                    for e in p.get("listed_in") or []:
                        if e["listing"] == L["slug"]:
                            by_paper.setdefault(p["arxiv_id"], []).append({**e, "raw": None})
                continue
            for e in L["entries"]:
                by_paper.setdefault(e["id"], []).append({"listing": L["slug"], "heading": e["heading"], "line": e["line"],
                                                         "url": e["url"], "link": e["link"], "raw": e["raw"]})
        replies = {r.url: r for L in found for r in L["replies"]}
        for aid in sorted(by_paper):
            es = sorted(by_paper[aid], key=lambda e: (e["listing"], e["line"]))
            slug = slug_for(aid)
            have = pw.have.get(slug) or {}
            old = {(e["listing"], e["heading"]) for e in have.get("listed_in") or []}
            listed = [{k: e[k] for k in ("listing", "heading", "line", "url", "link")} for e in es]
            first = es[0]
            ev = {"arxiv_id": {"quote": first["link"], "span": {"line": first["line"]}},
                  "title": {"quote": first["link"], "span": {"line": first["line"]}},
                  "listed_in": {"quote": first["link"], "span": {"line": first["line"], "heading": first["heading"]}},
                  "listing_count": {"quote": ", ".join(sorted({e["listing"] for e in es})), "span": {"pointer": "listed_in"}}}
            r = replies.get(first["raw"])
            pw.put(slug, {"arxiv_id": aid, "listed_in": listed, "listing_count": len({e["listing"] for e in es})},
                   have.get("title") or aid, self.of(r) if r else self.file_source, ev)
            st["listed_in"] += len({(e["listing"], e["heading"]) for e in es} - old)
            done = set()
            for e in es:
                if e["listing"] in done or e["listing"] not in ids:
                    continue
                done.add(e["listing"])
                rr = replies.get(e["raw"]) if e.get("raw") else None
                self.ctx.relate("paper", pw.have[slug]["id"], "listedIn", "listing", ids[e["listing"]],
                                source=self.source(rr.url, rr.body, "text/plain") if rr else None, quote=e["link"],
                                span={"heading": e["heading"], "line": e["line"], "url": e["url"]})
        for L in found:                                      # a saved search's answer is arXiv's metadata for its results
            if L["kind"] == "query" and L["replies"]:
                self.apply(L["atom"], self.of(L["replies"][0], "application/atom+xml"))
        st["papers_new"] = len(pw.created)

    # ---------------------------------------------------------------- pass 2: metadata

    def apply(self, recs, source):
        """arXiv's values for each paper in an answer, each citing the Atom element it came from."""
        for rec in recs:
            quotes = {k: {"quote": q, "span": {"pointer": f"entry {rec['arxiv_id']}"}} for k, q in rec["quotes"].items()}
            repos = find_repositories(rec.get("abstract"), rec.get("comment"))
            fields = {k: v for k, v in rec.items() if k not in ("quotes", "title")}
            fields.update(metadata_status="found", repositories=[r for r, _ in repos])
            quotes["metadata_status"] = quotes["arxiv_id"]
            quotes["title"] = quotes.get("title") or quotes["arxiv_id"]
            where = {"quote": repos[0][1], "span": {"pointer": "abstract or comment"}} if repos else \
                {"quote": "no github.com link in the abstract or comment", "span": {"pointer": "abstract, comment"}}
            quotes["repositories"] = where
            if not repos:                                     # nothing to ask GitHub: the rule is already decided
                fields["testable"], fields["testable_why"] = rule([], {})
                quotes["testable"] = quotes["testable_why"] = where
            _, ch = self.papers.put(slug_for(rec["arxiv_id"]), fields, rec.get("title") or rec["arxiv_id"], source, quotes)
            self.stats["metadata"] += ch

    def metadata_pass(self):
        pw = self.papers
        todo = sorted((p for p in pw.have.values() if not p.get("metadata_status")),
                      key=lambda p: (-(p.get("listing_count") or 0), p["arxiv_id"]))
        ids = [p["arxiv_id"] for p in todo]
        limit = int(self.inputs.get("batches", 80))
        for n in range(0, min(len(ids), limit * 100), 100):
            batch = ids[n:n + 100]
            url = f"{ARXIV_API}?id_list={','.join(batch)}&start=0&max_results=100"
            r = self.fetcher.get(url, max_age=10 ** 9)
            if r is None or not r.ok:
                self.ctx.log(f"arXiv did not answer for {len(batch)} identifiers; the next run resumes from here")
                return
            recs = parse_atom(r.text())
            self.apply(recs, self.of(r, "application/atom+xml"))
            got = {rec["arxiv_id"] for rec in recs}
            for aid in batch:
                if aid not in got:                            # arXiv has no entry: say so once, do not ask again
                    slug = slug_for(aid)
                    _, ch = pw.put(slug, {"metadata_status": "not found"}, pw.have[slug].get("title") or aid, self.of(r, "application/atom+xml"),
                                   {"metadata_status": {"quote": f"no <entry> for {aid} among {len(recs)} entries", "span": {"pointer": "feed"}}})
                    self.stats["not_found"] += ch
        left = len(ids) - min(len(ids), limit * 100)
        if left:
            self.ctx.log(f"{left} papers still have no metadata (batches limit {limit}); the next run resumes")

    # ---------------------------------------------------------------- pass 3: citations (OpenAlex)

    def citations_pass(self):
        pw, fetcher = self.papers, self.fetcher
        if not fetcher.replay and not fetcher.openalex_key:
            self.ctx.log("citations: skipped, no OpenAlex key (set OPENALEX_API in .env)")
            return
        today = self.inputs.get("today") or date.today().isoformat()
        cutoff = (date.fromisoformat(today) - timedelta(days=30)).isoformat()
        todo = sorted((p for p in pw.have.values() if (p.get("citations_checked") or "") <= cutoff),
                      key=lambda p: (-(p.get("listing_count") or 0), p["arxiv_id"]))
        limit, used = int(self.inputs.get("calls", 200)), 0
        for n in range(0, len(todo), 100):
            batch = todo[n:n + 100]
            dois = {"https://doi.org/10.48550/arxiv." + p["arxiv_id"].lower(): p for p in batch}
            url = ("https://api.openalex.org/works?filter=doi:"
                   + "|".join("https://doi.org/10.48550/arXiv." + p["arxiv_id"] for p in batch)
                   + "&per_page=100&select=id,doi,cited_by_count,primary_location")
            cached = url in fetcher.index
            if used >= limit and not cached and not fetcher.replay:
                break
            before = fetcher.requests
            r = fetcher.get(url, max_age=10 ** 9)
            used += fetcher.requests - before
            if r is None or not r.ok:
                self.ctx.log("OpenAlex did not answer; the next run resumes from here")
                break
            results = json.loads(r.body).get("results") or []
            by_doi = {(w.get("doi") or "").lower(): (i, w) for i, w in enumerate(results)}
            day = r.read_at[:10]
            for doi, p in dois.items():
                i, w = by_doi.get(doi, (None, None))
                slug = slug_for(p["arxiv_id"])
                if w is None:
                    fields = {"citations_checked": day}
                    ev = {"citations_checked": {"quote": f"no work with {doi} among {len(results)} results", "span": {"pointer": "/results"}}}
                else:
                    src = w.get("primary_location") or {}
                    venue = (src.get("source") or {}).get("display_name")
                    fields = {"openalex_id": w["id"].rsplit("/", 1)[-1], "citations": w.get("cited_by_count"), "venue": venue,
                              "citations_checked": day}
                    ev = {"openalex_id": key_quote("id", w["id"], f"/results/{i}/id"),
                          "citations": key_quote("cited_by_count", w.get("cited_by_count"), f"/results/{i}/cited_by_count"),
                          "citations_checked": key_quote("cited_by_count", w.get("cited_by_count"), f"/results/{i}/cited_by_count")}
                    if venue:
                        ev["venue"] = key_quote("display_name", venue, f"/results/{i}/primary_location/source/display_name")
                _, ch = pw.put(slug, fields, p["title"], self.of(r, "application/json"), ev)
                self.stats["cited"] += ch
        left = sum(1 for p in pw.have.values() if (p.get("citations_checked") or "") <= cutoff)
        self.ctx.log(f"citations: {used} OpenAlex list calls used (limit {limit}, about {used * 0.0001:.4f} USD); {left} papers not checked yet or older than 30 days")

    # ---------------------------------------------------------------- pass 4: testable

    def testable_pass(self):
        pw, fetcher = self.papers, self.fetcher
        todo = sorted((p for p in pw.have.values() if p.get("repositories") and p.get("testable") is None),
                      key=lambda p: (-(p.get("listing_count") or 0), p["arxiv_id"]))
        budget = int(self.inputs.get("checks", 100))
        left = fetcher.github_budget()
        if left is not None:
            budget = min(budget, left)
        checks, replies, used, stopped = {}, {}, 0, False
        for p in todo:
            for repo in p["repositories"]:
                if repo in checks:
                    continue
                url = f"https://api.github.com/repos/{repo}"
                cached = url in fetcher.index and fetcher.index[url]["status"] in (200, 404)
                if not cached and not fetcher.replay and (used >= budget or fetcher.github_left == 0):
                    stopped = True
                    break
                before = fetcher.requests
                r = fetcher.get(url, max_age=86400)
                used += fetcher.requests - before
                checks[repo] = read_repo(r)
                replies[repo] = r
            ok, why = rule(p["repositories"], checks)
            if ok is None:
                if stopped:
                    break
                continue
            first = next(r for r in p["repositories"] if checks.get(r))
            decider = next((r for r in p["repositories"] if checks.get(r) and one_ok(r, checks[r])), first)
            c = checks[decider]
            quote_ = ({"quote": f'"license": {{"spdx_id": {json.dumps(c.get("licence"))}}}, "archived": {json.dumps(c.get("archived"))}',
                       "span": {"pointer": "/license/spdx_id, /archived"}} if c.get("found") else
                      {"quote": "HTTP 404", "span": {"pointer": "status"}})
            rows = [{"repo": r, **{k: v for k, v in checks[r].items() if v is not None}} for r in p["repositories"] if checks.get(r)]
            _, ch = pw.put(slug_for(p["arxiv_id"]), {"testable": ok, "testable_why": why, "repo_checks": rows}, p["title"],
                           self.of(replies[decider], "application/json"),
                           {"testable": quote_, "testable_why": quote_, "repo_checks": quote_})
            self.stats["checked"] += ch
            self.stats["testable"] += bool(ok and ch)
        remaining = sum(1 for p in pw.have.values() if p.get("repositories") and p.get("testable") is None)
        if remaining:
            reason = "GitHub's rate limit or the checks limit" if stopped else "repositories it could not read"
            self.ctx.log(f"{remaining} papers with a repository are not checked yet ({reason}); the next run resumes, most-listed first"
                         + ("" if default_token() else "; GitHub is read without a login (60 requests an hour): set WB_PAPERS_GITHUB_TOKEN for more"))

    # ---------------------------------------------------------------- what the run says

    def summary(self):
        s, pw = self.stats, self.papers
        total = {"listings": len(self.listings.have), "papers": len(pw.have),
                 "listed_in": sum(len(p.get("listed_in") or []) for p in pw.have.values()),
                 "with_repository": sum(1 for p in pw.have.values() if p.get("repositories")),
                 "testable": sum(1 for p in pw.have.values() if p.get("testable")),
                 "checked": sum(1 for p in pw.have.values() if p.get("testable") is not None and p.get("repositories"))}
        wrote = (s["listings"] + s["papers_new"] + s["listed_in"] + s["metadata"] + s["not_found"] + s["cited"] + s["checked"])
        self.ctx.log(f"this run wrote: {s['listings']} listings, {s['papers_new']} new papers, {s['listed_in']} listed-in entries, "
                     f"metadata for {s['metadata']} papers ({s['not_found']} not on arXiv), citations for {s['cited']} papers, {s['checked']} papers checked for testable "
                     f"({s['testable']} testable); {self.fetcher.requests} requests, {self.fetcher.recorded} fetches recorded"
                     + ("; nothing was written" if not wrote and not self.fetcher.recorded else ""))
        self.ctx.log(f"the catalog holds: {total['listings']} listings, {total['papers']} papers, {total['listed_in']} listed-in entries, "
                     f"{total['with_repository']} papers with a repository, {total['checked']} of them checked, {total['testable']} testable")
        return {**s, "requests": self.fetcher.requests, "recorded": self.fetcher.recorded, "total": total}


def one_ok(repo, c):
    from papers_lib import one_repo
    return one_repo(repo, c)[0]


def register(wb):
    root = Path(wb.setting("root") or PACKAGE.parents[1])

    def run(*passes):
        def extractor(ctx, inputs):
            h = Harvest(ctx, inputs, root)
            for name in passes:
                getattr(h, name)()
            h.summary()
        return extractor

    wb.extractor("listings", run("listings_pass"), "listings.yaml: each list's arXiv identifiers with their headings and lines, each saved arXiv search's results; the papers they name")
    wb.extractor("metadata", run("metadata_pass"), "each paper's metadata from arXiv's API, 100 at a time, one request every 3 seconds, most-listed first (batches=N)")
    wb.extractor("citations", run("citations_pass"), "each paper's OpenAlex id, citation count and venue by its arXiv DOI, 100 to a list call, most-listed first (calls=N, default 200); needs an OpenAlex key")
    wb.extractor("testable", run("testable_pass"), "each paper with a repository, testable by rule from GitHub's licence and archived values; most-listed first, resumes (checks=N)")
    wb.extractor("harvest", run("listings_pass", "metadata_pass", "citations_pass", "testable_pass"), "listings, metadata, citations, then testable")
