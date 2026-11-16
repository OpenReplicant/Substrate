"""The paper catalog's leg one, on recorded pages (tests/fixtures), no network and no model: a list's identifiers and
headings, arXiv's Atom answers, the testable rule, and a whole run in a throwaway database: a paper two listings name is one
item with two listed-in entries, old and new identifier forms, every value with a source, and a second run that writes nothing.

    WORKBENCH_ADMIN_URL=postgresql://postgres:...@127.0.0.1:5432/postgres python3 packages/papers/tests/test_papers.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "workbench"), str(ROOT / "packages/papers/plugin")]
os.environ["WORKBENCH_DB"] = DB = f"workbench_test_{os.getpid()}"
os.environ.setdefault("WORKBENCH_JWT_SECRET", "p-" + "z" * 40)

import psycopg  # noqa: E402
from psycopg import sql  # noqa: E402

import papers_lib as lib  # noqa: E402
from workbench import cli  # noqa: E402
from workbench.extract import Plugins, run_extractor  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print(("ok  " if ok else "FAIL"), name, "" if ok else detail)


FIX = HERE / "fixtures"

# ---- a list's links
entries, other = lib.parse_list((FIX / "readme-one.md").read_text())
got = [(e["id"], e["heading"], e["line"]) for e in entries]
check("new and old identifiers, versions stripped, a pdf link read",
      [g[0] for g in got] == ["2309.02427", "cs/0112017", "2401.00001"], got)
check("each identifier keeps the path of headings it sat under", got[0][1] == "Agents > Memory" and got[2][1] == "Agents > Planning", got)
check("the line of the link is kept", got[0][2] == 5, got)
check("a link inside a code fence is not read", all(e["id"] != "9999.99999" for e in entries))
check("a paper link without an arXiv identifier is counted, not resolved", other == ["https://aclanthology.org/2023.acl-long.1/"], other)
check("nothing of the list's description is kept", all(set(e) == {"id", "heading", "line", "link"} for e in entries)
      and "copied" not in json.dumps(entries))
check("links of other shapes name the same identifiers",
      [lib.arxiv_id(u) for u in ("https://arxiv.org/abs/2309.02427v2", "http://export.arxiv.org/pdf/2309.02427.pdf",
                                 "https://www.alphaxiv.org/abs/2309.02427", "https://huggingface.co/papers/2309.02427",
                                 "https://arxiv.org/abs/hep-th/9901001v2", "https://arxiv.org/abs/math.GT/0309136",
                                 "https://arxiv.org/a/someone", "https://arxiv.org/abs/12345")]
      == ["2309.02427"] * 4 + ["hep-th/9901001", "math.GT/0309136", None, None])
check("a slug from an old identifier", lib.slug_for("cs/0112017") == "cs-0112017" and lib.slug_for("2309.02427") == "2309.02427")

# ---- arXiv's answer
recs = lib.parse_atom((FIX / "atom-batch.xml").read_text())
a = recs[0]
check("title, authors, dates, categories, doi, comment from the Atom elements",
      a["arxiv_id"] == "2309.02427" and a["title"].startswith("Cognitive") and a["authors"] == ["T. Sumers", "S. Yao"]
      and a["published"] == "2024-01-02" and a["categories"] == ["cs.AI", "cs.CL"] and a["doi"] == "10.1/x", a)
check("a value's quote is the element it was read from", a["quotes"]["title"].startswith("<title>") and a["quotes"]["doi"].startswith("<arxiv:doi>"), a["quotes"])
check("an abstract's whitespace is normalised", a["abstract"] == "We propose CoALA. It has parts.", a["abstract"])
check("repositories are found by pattern, .git and the closing dot dropped",
      [r for r, _ in lib.find_repositories(a["abstract"], a["comment"])] == ["o/mit-lib"]
      and [r for r, _ in lib.find_repositories("Code: github.com/o/gpl-lib.git, more")] == ["o/gpl-lib"])

# ---- the testable rule: three outcomes
mit = {"found": True, "licence": "MIT", "archived": False}
ok, why = lib.rule(["o/a"], {"o/a": mit})
check("testable: a repository, a permissive licence, not archived", ok is True and 'license.spdx_id="MIT"' in why and "archived=false" in why, why)
ok, why = lib.rule([], {})
check("not testable: no repository", ok is False and "no GitHub repository" in why, why)
ok, why = lib.rule(["o/a"], {"o/a": {**mit, "licence": "GPL-3.0"}})
check("not testable: a licence that is not permissive, quoted", ok is False and 'license.spdx_id="GPL-3.0"' in why, why)
ok, why = lib.rule(["o/a"], {"o/a": {**mit, "licence": None}})
check("not testable: no licence reported", ok is False and "no licence" in why, why)
ok, why = lib.rule(["o/a"], {"o/a": {**mit, "archived": True}})
check("not testable: archived", ok is False and "archived=true" in why, why)
ok, why = lib.rule(["o/a", "o/b"], {"o/a": {**mit, "licence": "GPL-2.0"}, "o/b": {**mit, "licence": "BSD-3-Clause"}})
check("one repository that passes is enough", ok is True and why.startswith("o/b"), why)
check("not decided while a repository is unread", lib.rule(["o/a"], {})[0] is None)
check("the permissive and LGPL licences", all(lib.permissive(x) for x in ("MIT", "Apache-2.0", "BSD-2-Clause", "ISC", "LGPL-3.0", "CC0-1.0", "Unlicense", "MPL-2.0"))
      and not any(lib.permissive(x) for x in ("GPL-3.0", "AGPL-3.0", "NOASSERTION", None, "CC-BY-4.0")))

# ---- rate limits: arXiv's 429, on a fake clock
import io  # noqa: E402
import urllib.error  # noqa: E402


class Fake:
    """A fake network and clock: answers in order (a status, or (status, Retry-After)); sleeping moves the clock."""

    def __init__(self, answers):
        self.answers, self.t, self.sleeps, self.calls, self.requests = list(answers), 1000.0, [], [], []

    def clock(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s

    def opener(self, req, timeout=0):
        self.calls.append(self.t)
        self.requests.append(req)
        a = self.answers.pop(0)
        status, retry = a if isinstance(a, tuple) else (a, None)
        if status != 200:
            raise urllib.error.HTTPError(req.full_url, status, "x", {"Retry-After": retry} if retry else {}, io.BytesIO(b""))

        class R(io.BytesIO):
            def __enter__(s):
                return s
            status, headers = 200, {}
        return R(b"<feed></feed>")


def fetcher(fake, d, **kw):
    return lib.Fetcher(Path(d), sleep=fake.sleep, clock=fake.clock, opener=fake.opener, **kw)


with tempfile.TemporaryDirectory() as d:
    f = Fake([429, 429, 200])
    r = fetcher(f, d).get("https://export.arxiv.org/api/query?id_list=1")
    check("a 429 from arXiv waits 30 s, then 60 s, and the batch goes through", r and r.ok and [s for s in f.sleeps if s >= 30] == [30, 60], f.sleeps)
    check("never faster than one request in three seconds, never two at once", all(b - a >= 3 for a, b in zip(f.calls, f.calls[1:])) and len(f.calls) == 3, f.calls)
with tempfile.TemporaryDirectory() as d:
    f = Fake([(503, "45"), 429, 429, 429])
    fe = fetcher(f, d)
    r = fe.get("https://export.arxiv.org/api/query?id_list=2")
    check("Retry-After is honoured, and after three waits (30, 60, 120 otherwise) it stops and the next run resumes",
          r is None and fe.waits == [45.0, 60.0, 120.0] and len(f.calls) == 4, (fe.waits, f.calls))
with tempfile.TemporaryDirectory() as d:
    f = Fake([200, 200])
    fe = fetcher(f, d, openalex_key="SECRETKEY123")
    fe.get("https://api.openalex.org/works?filter=doi:x")
    fe.get("https://export.arxiv.org/api/query?id_list=3")
    h = {r.full_url.split("/")[2]: dict(r.header_items()) for r in f.requests}
    kept = " ".join(p.read_text() if p.suffix != ".gz" else "" for p in Path(d).rglob("*") if p.is_file())
    check("the OpenAlex key is sent as a bearer header to OpenAlex only, never in a URL or the record",
          h["api.openalex.org"].get("Authorization") == "Bearer SECRETKEY123" and "Authorization" not in h["export.arxiv.org"]
          and not any("SECRETKEY123" in r.full_url for r in f.requests) and "SECRETKEY123" not in kept)
    check("requests say paper-catalog/0.1 and nothing about who asks", all(r.get_header("User-agent") == "paper-catalog/0.1" for r in f.requests))

# ---- a whole run, on recorded pages, in a throwaway database
INPUT = {"replay": str(FIX), "listings": str(FIX / "listings.yaml"), "today": "2026-11-17"}


def snapshot(conn):
    return {"claims": conn.execute("select count(*) from wb.claim").fetchone()[0],
            "sources": conn.execute("select count(*) from wb.source").fetchone()[0],
            "relations": conn.execute("select count(*) from wb.relation").fetchone()[0],
            "papers": conn.execute("select count(*), max(updated_at) from content.paper").fetchone(),
            "listings": conn.execute("select count(*), max(updated_at) from content.listing").fetchone()}


try:
    cli.migrate()
    cli.load_plugin(ROOT / "packages/papers/plugin")
    with tempfile.TemporaryDirectory() as d:
        os.symlink(ROOT / "packages/papers/plugin", Path(d) / "papers")
        plugins = Plugins().load(Path(d))
        check("the plugin loads with its five extractors", sorted(k for k in plugins.extractors if k.startswith("papers:")) ==
              ["papers:citations", "papers:harvest", "papers:listings", "papers:metadata", "papers:testable"], plugins.loaded)
        os.environ.pop("WB_PAPERS_OPENALEX_KEY", None)
        r0 = run_extractor(cli.connect, plugins, "papers:citations", {"listings": str(FIX / "listings.yaml")})
        check("without an OpenAlex key the citation pass is skipped and says so", r0.get("ok") and any("skipped, no OpenAlex key" in m for m in r0["log"]), r0)
        first = run_extractor(cli.connect, plugins, "papers:harvest", INPUT)
        check("the run succeeds", first.get("ok"), first)
        print("   ", *first.get("log", []), sep="\n    ")
        with cli.connect() as conn:
            papers = {r[0]: r for r in conn.execute(
                "select slug, arxiv_id, title, listing_count, listed_in, repositories, testable, testable_why, metadata_status from api.paper")}
            listings = {r[0]: r for r in conn.execute("select slug, kind, licence, stars, entries, unresolved, machine_built, last_changed from api.listing")}
            check("three listings: two lists and a saved search", sorted(listings) == ["a-one", "arxiv-query-dual", "b-two"], sorted(listings))
            check("a list's licence is as GitHub reports it, or none reported", listings["a-one"][2] == "none reported" and listings["b-two"][2] == "MIT", listings)
            check("a list's counts: entries and unresolved links", listings["a-one"][4:6] == (3, 1) and listings["b-two"][4:6] == (2, 0), listings)
            check("machine-built is the listings file's word", listings["b-two"][6] is True and listings["a-one"][6] is False)
            check("five papers: old and new identifiers, one item each", sorted(papers) ==
                  ["2309.02427", "2401.00001", "2402.00002", "2403.00003", "cs-0112017"], sorted(papers))
            p = papers["2309.02427"]
            check("a paper two lists name is one item with two listed-in entries", p[3] == 2 and len(p[4]) == 2
                  and {e["listing"] for e in p[4]} == {"a-one", "b-two"}, p[4])
            check("each entry keeps its heading and cites its line", {e["heading"] for e in p[4]} == {"Agents > Memory", "Survey > Cognition"}
                  and all("#L" in e["url"] and e["link"].startswith("https://arxiv.org/abs/2309.02427") for e in p[4]), p[4])
            rel = conn.execute("""select l.slug, c.quote, c.span->>'heading', s.uri from wb.relation r join content.listing l on l.id = r.to_id
                                  join content.paper p on p.id = r.from_id join wb.claim c on c.subject_id = p.id and c.object_id = l.id and c.status = 'current'
                                  join wb.source s on s.id = c.source_id where p.slug = '2309.02427' and r.predicate = 'listedIn' order by 1""").fetchall()
            check("and two listedIn relations, each citing the list's page and the link found",
                  [x[0] for x in rel] == ["a-one", "b-two"] and rel[0][3].endswith("a/one/HEAD/README.md") and rel[0][1].startswith("https://arxiv.org/abs/2309"), rel)
            check("metadata arrived: the title, with its Atom element as the quote", p[2] == "Cognitive Architectures for Language Agents" and p[8] == "found")
            q = conn.execute("""select c.quote, s.uri, c.author from wb.claim c join wb.source s on s.id = c.source_id where c.subject_id = (select id from content.paper where slug = '2309.02427')
                                and c.field = 'title' and c.status = 'current' and c.quote is not null""").fetchall()
            check("the title claim quotes <title> and cites the arXiv request", q and q[0][0].startswith("<title>") and "export.arxiv.org/api/query?id_list=" in q[0][1], q)
            bare = conn.execute("""select c.field from wb.claim c where c.subject_type = 'paper' and c.object_id is null and c.status = 'current'
                                   and c.field not in ('listing_count', 'slug') and (c.source_id is null or c.quote is null)""").fetchall()
            check("every value of every paper has a source and a quote", not bare, bare)
            check("a paper only a saved search found is in it, under its topic", papers["2403.00003"][4][0]["heading"] == "dual-process agents"
                  and papers["2403.00003"][4][0]["listing"] == "arxiv-query-dual", papers["2403.00003"][4])
            check("an old-style identifier is an item, with its own slug", papers["cs-0112017"][1] == "cs/0112017" and papers["cs-0112017"][2] == "Old paper")
            check("repositories by pattern", papers["2309.02427"][5] == ["o/mit-lib"] and papers["2401.00001"][5] == ["o/gpl-lib"]
                  and papers["cs-0112017"][5] == [] and papers["2402.00002"][5] == ["o/archived"], {k: v[5] for k, v in papers.items()})
            check("testable, outcome one: permissive and not archived", papers["2309.02427"][6] is True and 'license.spdx_id="MIT"' in papers["2309.02427"][7], papers["2309.02427"][7])
            check("not testable, outcome two: a GPL repository", papers["2401.00001"][6] is False and "GPL-3.0" in papers["2401.00001"][7], papers["2401.00001"][7])
            check("not testable, outcome three: archived", papers["2402.00002"][6] is False and "archived=true" in papers["2402.00002"][7], papers["2402.00002"][7])
            check("not testable: a repository GitHub does not have; and none named", papers["2403.00003"][6] is False and "404" in papers["2403.00003"][7]
                  and papers["cs-0112017"][6] is False, (papers["2403.00003"][7], papers["cs-0112017"][6]))
            tc = conn.execute("""select c.quote, s.uri from wb.claim c join wb.source s on s.id = c.source_id where c.subject_id = (select id from content.paper where slug = '2309.02427')
                                 and c.field = 'testable' and c.status = 'current'""").fetchall()
            check("the testable claim quotes GitHub's licence and archived values and cites its API answer",
                  tc and '"spdx_id": "MIT"' in tc[0][0] and tc[0][1] == "https://api.github.com/repos/o/mit-lib", tc)
            texts = " ".join(str(r[0]) for r in conn.execute("select quote from wb.claim where quote is not null"))
            check("no list description was copied into a claim", "must not be copied" not in texts and "description" not in texts)
            c = {r[0]: r[1:] for r in conn.execute("select slug, openalex_id, citations, venue, citations_checked from api.paper")}
            check("citations: id, count, venue (when OpenAlex names one) and the day checked", c["2309.02427"] == ("W4386528753", 510, "Transactions on Machine Learning Research", "2026-11-16")
                  and c["2402.00002"] == ("W111", 7, None, "2026-11-16"), c)
            check("a paper OpenAlex does not have is marked checked, with no count", c["cs-0112017"] == (None, None, None, "2026-11-16") and c["2403.00003"][1] is None, c)
            cc = conn.execute("""select c.quote, s.uri from wb.claim c join wb.source s on s.id = c.source_id where c.subject_id = (select id from content.paper where slug = '2309.02427')
                                 and c.field = 'citations' and c.status = 'current'""").fetchall()
            check("the citations claim quotes cited_by_count and cites the request URL, which carries no key",
                  cc and cc[0][0] == '"cited_by_count": 510' and cc[0][1].startswith("https://api.openalex.org/works?filter=doi:") and "key" not in cc[0][1].lower(), cc)
            check("the log says how many list calls were used", any("citations: 0 OpenAlex list calls used" in m for m in first["log"]), first["log"])
            before = snapshot(conn)
        second = run_extractor(cli.connect, plugins, "papers:harvest", INPUT)
        print("   ", *second.get("log", []), sep="\n    ")
        with cli.connect() as conn:
            after = snapshot(conn)
        check("a second run over unchanged sources writes nothing: no claim, source, relation or item", before == after, (before, after))
        check("and says so", any("nothing was written" in m for m in second["log"]), second["log"])
        third = run_extractor(cli.connect, plugins, "papers:harvest", {**INPUT, "listings": str(FIX / "listings.yaml")})
        with cli.connect() as conn:
            check("a third run too", snapshot(conn) == before)
finally:
    with psycopg.connect(cli.url("postgres"), autocommit=True) as conn:
        conn.execute(sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(DB)))

print(f"{sum(checks)}/{len(checks)} checks passed")
sys.exit(0 if all(checks) else 1)
