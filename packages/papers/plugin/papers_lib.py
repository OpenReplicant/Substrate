"""The paper catalog's plain code, no model and no database: reading a list's links, arXiv's Atom answers and
GitHub's repository answers, the testable rule, and the recording fetch.

Every fetch is recorded under `.state/papers/` (an index of {url, read_at, sha256, status, bytes} and each body once,
by hash), so a run can be replayed (`replay=DIR`) and tests use small recorded pages. arXiv is asked once every three
seconds on one connection (its terms); the requests say `paper-catalog/0.1` and nothing else about who asks.
"""
from __future__ import annotations

import gzip
import hashlib
import html
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

USER_AGENT = "paper-catalog/0.1"
ARXIV_API = "https://export.arxiv.org/api/query"
ARXIV_GAP = 3.0                       # seconds between arXiv requests (https://info.arxiv.org/help/api/tou.html)
PERMISSIVE = {"MIT", "Apache-2.0", "ISC", "CC0-1.0", "Unlicense", "MPL-2.0"}
PERMISSIVE_PREFIX = ("BSD-", "LGPL-")


# ---- the recording fetch

class Reply:
    def __init__(self, url, status, body, read_at, fresh=False, stale=False):
        self.url, self.status, self.body, self.read_at, self.fresh, self.stale = url, status, body, read_at, fresh, stale
        self.sha256 = hashlib.sha256(body).hexdigest()

    @property
    def ok(self):
        return self.status == 200

    def text(self):
        return self.body.decode("utf-8", "replace")


class Fetcher:
    """GET with a record. `replay` reads only a recorded directory (never the network). Otherwise a URL read less than
    `max_age` seconds ago (per host family, see age()) is answered from the record; a failed read falls back to the
    last recording of that URL (stale). A body is written to the record only when it differs from the last one."""

    def __init__(self, state: Path | None, replay: Path | None = None, max_age: float = 3600, token: str | None = None,
                 sleep=time.sleep, clock=time.time, openalex_key: str | None = None, opener=None):
        self.dir, self.replay, self.max_age, self.token = Path(state) if state else None, Path(replay) if replay else None, max_age, token
        self.sleep, self.clock, self.openalex_key = sleep, clock, openalex_key
        self.opener = opener or urllib.request.urlopen
        self.waits: list[float] = []                   # every pause for a rate limit, for the log and the tests
        self.recorded, self.requests, self.last_arxiv = 0, 0, 0.0
        self.github_left: int | None = None            # GitHub's remaining requests, once it has said
        self.index: dict[str, dict] = {}
        for d in (self.replay or self.dir,):
            f = d / "fetches.jsonl" if d else None
            if f and f.is_file():
                for line in f.read_text().splitlines():
                    if line.strip():
                        e = json.loads(line)
                        self.index[e["url"]] = e          # the newest line for a URL wins

    def _body(self, e: dict) -> bytes | None:
        base = self.replay or self.dir
        if e.get("file"):
            return (base / e["file"]).read_bytes()
        p = base / "bodies" / (e["sha256"] + ".gz")
        return gzip.decompress(p.read_bytes()) if p.is_file() else None

    def _recorded(self, url, **kw) -> Reply | None:
        e = self.index.get(url)
        body = self._body(e) if e else None
        return Reply(url, e["status"], body, e["read_at"], **kw) if body is not None else None

    def github_budget(self) -> int | None:
        """What GitHub's API will still answer this hour (its /rate_limit does not count), None if unknown or replaying."""
        if self.replay:
            return None
        if self.github_left is None:
            try:
                with self.opener(self._request("https://api.github.com/rate_limit"), timeout=30) as r:
                    self.github_left = int(json.loads(r.read())["resources"]["core"]["remaining"])
            except (urllib.error.URLError, OSError, ValueError, KeyError):
                return None
        return self.github_left

    def _request(self, url):
        h = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json" if "api.github.com" in url else "*/*"}
        if self.token and "api.github.com" in url:
            h["Authorization"] = "Bearer " + self.token        # never recorded, never logged
        if self.openalex_key and "api.openalex.org" in url:
            h["Authorization"] = "Bearer " + self.openalex_key  # only as this header: never in a URL, a record or a log
        return urllib.request.Request(url, headers=h)

    def get(self, url: str, max_age: float | None = None) -> Reply | None:
        if self.replay:
            return self._recorded(url)
        age = self.max_age if max_age is None else max_age
        e = self.index.get(url)
        if e and e["status"] in (200, 404) and self.clock() - _epoch(e["read_at"]) < age:
            return self._recorded(url)
        if "api.github.com" in url and self.github_left is not None and self.github_left <= 0:
            return self._recorded(url, stale=True)         # rate-limited: the earlier answer, or nothing
        retry = [30, 60, 120] if "arxiv.org" in url else [2, 5] if "openalex.org" in url else []
        for attempt in range(len(retry) + 1):
            if "arxiv.org" in url:                          # one connection, one request every three seconds at most
                wait = self.last_arxiv + ARXIV_GAP - self.clock()
                if wait > 0:
                    self.sleep(wait)
            try:
                with self.opener(self._request(url), timeout=60) as r:
                    status, body, headers = r.status, r.read(), r.headers
            except urllib.error.HTTPError as err:
                status, body, headers = err.code, err.read() or b"", err.headers
            except (urllib.error.URLError, OSError):
                status, body, headers = 0, b"", {}
            if "arxiv.org" in url:
                self.last_arxiv = self.clock()
            self.requests += 1
            if status not in (429, 503) or attempt == len(retry):
                break
            try:                                            # the server's own Retry-After wins, within reason
                pause = min(float(headers.get("Retry-After")), 600.0)
            except (TypeError, ValueError):
                pause = float(retry[attempt])
            self.waits.append(pause)
            self.sleep(pause)
        if "api.github.com" in url and headers.get("X-RateLimit-Remaining") is not None:
            self.github_left = int(headers["X-RateLimit-Remaining"])
        if status in (200, 404) and not (status == 404 and "github.com" not in url):
            reply = Reply(url, status, body, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.clock())), fresh=True)
            self._record(reply)
            return reply
        return self._recorded(url, stale=True)             # 403 (rate limit), 5xx, no network: the last good answer, or None

    def _record(self, r: Reply):
        if not self.dir:
            raise RuntimeError("no place to record fetches (.state/papers is not writable here); run it with scripts/workbench.sh extract")
        last = self.index.get(r.url)
        if last and last["sha256"] == r.sha256 and last["status"] == r.status:
            return                                            # unchanged: nothing is written
        (self.dir / "bodies").mkdir(parents=True, exist_ok=True)
        body = self.dir / "bodies" / (r.sha256 + ".gz")
        if not body.exists():
            body.write_bytes(gzip.compress(r.body, mtime=0))
        entry = {"url": r.url, "read_at": r.read_at, "sha256": r.sha256, "status": r.status, "bytes": len(r.body)}
        with open(self.dir / "fetches.jsonl", "a") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")
        self.index[r.url] = entry
        self.recorded += 1


def _epoch(stamp: str) -> float:
    import calendar
    return calendar.timegm(time.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ"))


def default_token() -> str | None:
    return os.environ.get("WB_PAPERS_GITHUB_TOKEN") or None


# ---- a paper list's links

NEW_ID = r"\d{4}\.\d{4,5}"
OLD_ID = r"[a-z][a-z-]*(?:\.[A-Za-z]{2})?/\d{7}"
ARXIV_LINK = re.compile(
    r"^https?://(?:www\.|export\.)?(?:arxiv\.org/(?:abs|pdf|html|format)|alphaxiv\.org/(?:abs|overview|pdf)|huggingface\.co/papers)/"
    rf"({NEW_ID}|{OLD_ID})(?:v\d+)?(?:\.pdf)?(?![\w.])")
URL = re.compile(r"https?://[^\s<>\"')\]]+")
OTHER_PAPER = re.compile(
    r"^https?://(?:[\w.-]+\.)?(?:aclanthology\.org|openreview\.net|doi\.org|semanticscholar\.org|proceedings\.mlr\.press|"
    r"proceedings\.neurips\.cc|papers\.nips\.cc|openaccess\.thecvf\.com|ieeexplore\.ieee\.org|dl\.acm\.org|link\.springer\.com|"
    r"nature\.com/articles|science\.org/doi|sciencedirect\.com|biorxiv\.org|ssrn\.com)|^https?://\S+\.pdf(?:[?#]|$)", re.I)


def arxiv_id(link: str) -> str | None:
    """The identifier an arXiv-looking link names, versions stripped: 2309.02427v3 gives 2309.02427; cs/0112017 stays."""
    m = ARXIV_LINK.match(link.rstrip(".,;:"))
    return m.group(1) if m else None


def slug_for(aid: str) -> str:
    return aid.lower().replace("/", "-")


def clean_heading(s: str) -> str:
    s = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"[*_`]+", "", s)
    return html.unescape(re.sub(r"\s+", " ", s)).strip(" #:")


def parse_list(text: str) -> tuple[list[dict], list[str]]:
    """(entries, unresolved) of a markdown or HTML-in-markdown paper list. An entry is {id, heading, line, link}: the arXiv
    identifier a link names, the path of headings above it ("A > B"), its line number and the link as found; the first
    time an identifier appears under a heading. Unresolved: links to papers elsewhere (ACL Anthology, DOI, ...) on lines
    that name no arXiv identifier, each URL once. Nothing else of the line is read."""
    entries, seen, other = [], set(), []
    stack: list[tuple[int, str]] = []
    fenced = False
    for n, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced:
            continue                                        # code blocks hold examples, not the list
        m = re.match(r"^\s{0,3}(#{1,6})\s+(.*)$", line)
        level, raw = (len(m.group(1)), m.group(2)) if m else (None, None)
        if not m and (h := re.match(r"^\s*<h([1-6])[^>]*>(.*?)</h\1>", line, re.I)):
            level, raw = int(h.group(1)), h.group(2)
        if level is not None:
            title = clean_heading(raw)
            if title:
                stack = [(lv, t) for lv, t in stack if lv < level] + [(level, title)]
            continue
        urls = URL.findall(line)
        found = [(i, u) for u in urls if (i := arxiv_id(u))]
        for aid, link in found:
            heading = " > ".join(t for _, t in stack)
            if (aid, heading) not in seen:
                seen.add((aid, heading))
                entries.append({"id": aid, "heading": heading, "line": n, "link": link})
        if not found:
            for u in urls:
                if OTHER_PAPER.match(u) and u not in other:
                    other.append(u)
    return entries, other


# ---- arXiv's Atom answers

def _elem(chunk: str, name: str, all_=False):
    pat = re.compile(rf"<{name}(?:\s[^>]*)?(?:/>|>(.*?)</{name}>)", re.S)
    found = [(m.group(0), html.unescape(m.group(1) or "")) for m in pat.finditer(chunk)]
    return found if all_ else (found[0] if found else (None, None))


def _norm(s: str | None) -> str | None:
    return " ".join(s.split()) if s else None


def parse_atom(raw: str) -> list[dict]:
    """Each paper in an arXiv API answer: its values and, per field, the Atom element it was read from."""
    out = []
    for m in re.finditer(r"<entry>(.*?)</entry>", raw, re.S):
        chunk = m.group(1)
        qid, text = _elem(chunk, "id")
        mid = re.match(rf"^https?://arxiv\.org/abs/({NEW_ID}|{OLD_ID})(?:v\d+)?$", (text or "").strip())
        if not mid:
            continue                                        # an error entry, not a paper
        rec = {"arxiv_id": mid.group(1)}
        quotes = {"arxiv_id": qid}
        for field, tag in (("title", "title"), ("abstract", "summary"), ("published", "published"), ("updated", "updated"),
                           ("doi", "arxiv:doi"), ("journal_ref", "arxiv:journal_ref"), ("comment", "arxiv:comment")):
            q, v = _elem(chunk, tag)
            v = _norm(v)
            if v:
                rec[field] = v[:10] if field in ("published", "updated") else v
                quotes[field] = q
        authors = [(q, _norm(n)) for q, _ in _elem(chunk, "author", True) for q, n in [_elem(q, "name")]]
        if authors:
            rec["authors"] = [n for _, n in authors if n]
            quotes["authors"] = " ".join(q for q, _ in authors)
        cats = [(q, re.search(r'term="([^"]+)"', q).group(1)) for q, _ in _elem(chunk, "category", True) if 'term="' in q]
        if cats:
            rec["categories"] = [c for _, c in cats]
            quotes["categories"] = " ".join(q for q, _ in cats)
        rec["quotes"] = {k: v[:600] for k, v in quotes.items() if v}
        out.append(rec)
    return out


REPO = re.compile(r"github\.com/([A-Za-z0-9][A-Za-z0-9_.-]*)/([A-Za-z0-9_.-]+)")


def find_repositories(*texts: str | None) -> list[tuple[str, str]]:
    """[(owner/name, the text it was found in)] for GitHub repositories named in the abstract or comment, once each."""
    found, seen = [], set()
    for text in texts:
        for m in REPO.finditer(text or ""):
            owner, name = m.group(1), re.sub(r"(\.git)?[.-]*$", "", m.group(2))
            if not name or owner.lower() in ("orgs", "sponsors", "topics", "features") or name.lower() in ("issues", "pulls"):
                continue
            key = f"{owner}/{name}".lower()
            if key not in seen:
                seen.add(key)
                found.append((f"{owner}/{name}", m.group(0)))
    return found


# ---- the testable rule

def permissive(spdx: str | None) -> bool:
    return bool(spdx) and (spdx in PERMISSIVE or spdx.startswith(PERMISSIVE_PREFIX))


def read_repo(reply: Reply | None) -> dict | None:
    """GitHub's answer for a repository: {found, licence, archived, stars, last_push} (None if there is no answer)."""
    if reply is None:
        return None
    if reply.status == 404:
        return {"found": False}
    try:
        d = json.loads(reply.body)
    except ValueError:
        return None
    return {"found": True, "licence": (d.get("license") or {}).get("spdx_id"), "archived": d.get("archived"),
            "stars": d.get("stargazers_count"), "last_push": (d.get("pushed_at") or "")[:10] or None}


def one_repo(repo: str, c: dict) -> tuple[bool, str]:
    if not c.get("found"):
        return False, f'{repo}: GitHub has no such repository (HTTP 404)'
    spdx, archived = c.get("licence"), c.get("archived")
    lic = f'license.spdx_id={json.dumps(spdx)}'
    arc = f'archived={json.dumps(archived)}'
    if not permissive(spdx):
        why = "GitHub reports no licence" if spdx is None else "not a permissive or LGPL licence"
        return False, f"{repo}: {lic} ({why}), {arc}"
    if archived:
        return False, f"{repo}: {lic} is permissive, but {arc}"
    return True, f"{repo}: {lic} is permissive, {arc}"


def rule(repos: list[str], checks: dict[str, dict | None]) -> tuple[bool | None, str]:
    """testable and why. True: a repository passes. False: none is named, or every one fails (each reason quoted).
    None: nothing passes yet and some repository has not been read."""
    if not repos:
        return False, "no GitHub repository is named in the abstract or comment"
    reasons, unread = [], False
    for repo in repos:
        c = checks.get(repo)
        if c is None:
            unread = True
            continue
        ok, why = one_repo(repo, c)
        if ok:
            return True, why
        reasons.append(why)
    return (None, "") if unread else (False, "; ".join(reasons))
