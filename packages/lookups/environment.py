"""The lookups environment (environment.yaml; docs/contracts/environment.md): `reset`, `step`, the encoders and
the recording fetch. Plain functions and one class; nothing here imports the store, so a judged run's driver and
the handlers plugin's live run use it alike.

    env = make(Record(path, network=False))      # judged: replay the record, never the network
    env = make(Record(None, network=True))       # live: read the registries, keep what was read
    obs = env.reset(case, seed); obs, reward, terminated, truncated, info = env.step(action); env.final()

An observation is a list of claims: {subject, property, value, source, time}. `reward` is always None: the score
is the scorer's, never something the agent is told.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
SPEC = yaml.safe_load((HERE / "environment.yaml").read_text())
# every environment has these two (the contract, "How it grows"): ask is the step loop's; propose_handler is
# always a proposal, recorded for a person
ALWAYS = {"ask": "free", "propose_handler": "propose"}
# a generic client name: a query carries the question's terms and nothing about who asks
USER_AGENT = "lookups-environment/0.1 (registry lookups)"


# ---- the recording fetch

class Record:
    """Every page read: {url, read_at, sha256, status, body}, keyed by URL. With `network`, a URL not in the record
    is read once and kept; without it, it is a miss (None), and the agent is told the page is not recorded."""

    def __init__(self, path: Path | str | None = None, network: bool = False):
        self.path, self.network, self.entries, self.new = (Path(path) if path else None), network, {}, []
        if self.path and self.path.is_file():
            opener = gzip.open if self.path.suffix == ".gz" else open
            with opener(self.path, "rt", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        e = json.loads(line)
                        self.entries[e["url"]] = e

    def get(self, url: str) -> dict | None:
        if url in self.entries:
            return self.entries[url]
        if not self.network:
            return None
        headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json" if "api.github.com" in url else "application/json"}
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
                status, body = r.status, r.read()
        except urllib.error.HTTPError as e:
            status, body = e.code, e.read() or b""
        except (urllib.error.URLError, OSError) as e:
            status, body = 0, str(e).encode()
        time.sleep(1)            # crates.io asks for about one request a second; the others are as polite
        e = {"url": url, "read_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "sha256": hashlib.sha256(body).hexdigest(),
             "status": status, "body": body.decode("utf-8", "replace")}
        self.entries[url] = e
        self.new.append(url)
        return e

    def save(self, path: Path | str | None = None):
        path = Path(path) if path else self.path
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "wt", encoding="utf-8") as f:
            for url in sorted(self.entries):
                f.write(json.dumps(self.entries[url], sort_keys=True) + "\n")


# ---- the registries, from the map

_MAP: dict = {}


def registries(spec: dict = SPEC, catalog: Path | None = None) -> dict:
    """{registry: {search: URL with QUERY or None, page: URL with NAME or None}}: the GET URLs the map's sources
    system gives in substrate.dev/search, with environment.yaml's `page` where the map has none."""
    catalog = catalog or HERE.parents[1] / "catalog-info.yaml"
    if catalog not in _MAP:            # read once a process
        _MAP[catalog] = {}
        for doc in yaml.safe_load_all(catalog.read_text()):
            meta, s = (doc or {}).get("metadata") or {}, (doc or {}).get("spec") or {}
            if s.get("system") == "sources":
                _MAP[catalog][meta.get("name")] = (meta.get("annotations") or {}).get("substrate.dev/search") or ""
    found = _MAP[catalog]
    out = {}
    for reg, cfg in (spec.get("registries") or {}).items():
        text = found.get(cfg["map"])
        if text is None:
            raise ValueError(f"the map has no {cfg['map']} in its sources system")
        urls = [u.rstrip(";,')") for u in re.findall(r"GET (https://\S+)", text)]
        out[reg] = {"search": next((u for u in urls if "QUERY" in u), None),
                    "page": cfg.get("page") or next((u for u in urls if "NAME" in u), None)}
    return out


# a registry's own web page, read as the JSON its API serves for the same thing
WEB = [(r"^https?://(?:www\.)?github\.com/([^/]+/[^/#?]+?)(?:\.git)?/?$", "https://api.github.com/repos/{}"),
       (r"^https?://pypi\.org/project/([^/]+)/?$", "https://pypi.org/pypi/{}/json"),
       (r"^https?://(?:www\.)?npmjs\.com/package/(.+?)/?$", "https://registry.npmjs.org/{}"),
       (r"^https?://crates\.io/crates/([^/]+)/?$", "https://crates.io/api/v1/crates/{}"),
       (r"^https?://huggingface\.co/(?!api/)([^/]+(?:/[^/]+)?)/?$", "https://huggingface.co/api/models/{}")]
ALIASES = {"pypi": "pypi", "python": "pypi", "npm": "npm", "npmjs": "npm", "crates": "crates", "cratesio": "crates",
           "cargo": "crates", "rust": "crates", "github": "github", "huggingface": "huggingface", "hf": "huggingface",
           "huggingfacehub": "huggingface"}


def claim(subject, prop, value, source=None, at=None) -> dict:
    return {"subject": subject, "property": prop, "value": value, "source": source, "time": at}


# ---- encoders: a reading into claims

def question_claims(case: dict) -> list[dict]:
    """The question only: a case's other fields (its shape, registry, name) are for people and the scorer."""
    return [claim(f"question:{case['id']}", "question", str(case.get("question") or "").strip(), f"question:{case['id']}", case.get("at"))]


def cut(v, n: int):
    return v if not isinstance(v, str) or len(v) <= n else v[:n] + "…"


def summary(v) -> str:
    keys = list(v) if isinstance(v, dict) else None
    if keys is None:
        return f"[{len(v)} items: fetch with a path ending /0 to read the first]"
    ends = keys[:3] + (["…"] + keys[-3:] if len(keys) > 6 else keys[3:])
    return f"{{{len(keys)} fields: {', '.join(map(str, ends))}}}"


def page_claims(entry: dict, path: str | None, view: dict) -> list[dict]:
    """A fetched body as path = value claims, breadth first, within the view's budget (environment.yaml)."""
    url, at = entry["url"], entry["read_at"]
    try:
        body = json.loads(entry["body"])
    except ValueError:
        return [claim(url, "text", cut(entry["body"], view["chars"]), url, at)]
    prefix = (path or "").strip("/")
    for key in [k for k in prefix.split("/") if k]:
        if isinstance(body, dict) and key in body:
            body = body[key]
        elif isinstance(body, list) and key.isdigit() and int(key) < len(body):
            body = body[int(key)]
        else:
            here = list(body)[:20] if isinstance(body, dict) else f"a list of {len(body)}" if isinstance(body, list) else "a value"
            return [claim(url, prefix, f"no field {key!r} here; what is there: {here}", url, at)]
    out, used, queue, shown = [], 0, deque([(prefix, body, True)]), 0
    total = 0
    while queue:
        p, v, root = queue.popleft()
        if isinstance(v, (dict, list)) and (root or len(v) <= view["expand"]) and v:
            items = v.items() if isinstance(v, dict) else enumerate(v)
            queue.extend((f"{p}/{k}" if p else str(k), x, False) for k, x in items)
            continue
        total += 1
        value = summary(v) if isinstance(v, (dict, list)) and v else cut(v, view["string"])
        size = len(p) + len(json.dumps(value, ensure_ascii=False)) + 3
        if used + size > view["chars"]:
            continue
        used += size
        shown += 1
        out.append(claim(url, p or "(whole)", value, url, at))
    if shown < total:
        out.append(claim(url, "not shown", f"{total - shown} more fields; fetch again with a path to read under one", url, at))
    return out


def hit_claims(registry: str, entry: dict, pages: dict) -> list[dict]:
    """A search's top five, each with the page to fetch for it."""
    url, at = entry["url"], entry["read_at"]
    try:
        d = json.loads(entry["body"])
    except ValueError:
        return [claim(url, "text", cut(entry["body"], 300), url, at)]
    page = pages[registry]["page"] or ""
    rows = []
    if registry == "npm":
        rows = [(p.get("name"), {"version": p.get("version"), "description": p.get("description")})
                for p in (o.get("package") or {} for o in d.get("objects") or [])]
    elif registry == "crates":
        rows = [(c.get("id"), {"version": c.get("max_stable_version") or c.get("newest_version"), "description": c.get("description")})
                for c in d.get("crates") or []]
    elif registry == "github":
        rows = [(r.get("full_name"), {"description": r.get("description")}) for r in d.get("items") or []]
    elif registry == "huggingface":
        rows = [(m.get("id"), {}) for m in (d if isinstance(d, list) else [])]
    out = []
    for name, fields in rows[:5]:
        if not name:
            continue
        subject = page.replace("NAME", name) if page else name
        out.append(claim(subject, "name", name, url, at))
        out += [claim(subject, k, cut(v, 120), url, at) for k, v in fields.items() if v]
    return out or [claim(url, "results", "none", url, at)]


# ---- the environment

class Lookups:
    def __init__(self, record: Record, spec: dict = SPEC, pages: dict | None = None):
        self.record, self.spec = record, spec
        self.pages = pages if pages is not None else registries(spec)
        self.gates = {**(spec.get("actions") or {}), **ALWAYS}
        self.max_steps = int((spec.get("episode") or {}).get("max_steps", 8))
        self.view = spec["observation"]
        self.done, self.case = True, None

    def actions(self) -> list[dict]:
        """The action kinds and their arguments, as the agent is told them (its tools)."""
        regs = ", ".join(self.pages)
        pages = "; ".join(f"{r}: {p['page']}" for r, p in self.pages.items() if p["page"])
        nosearch = ", ".join(r for r, p in self.pages.items() if not p["search"])
        return [
            {"kind": "search", "description": f"Search a registry ({regs}) for packages by name or words; the top five, each with "
                                              f"its page to fetch. No search on: {nosearch or 'none'}.",
             "arguments": {"registry": "one of " + regs, "query": "the words to search for"}, "required": ["registry", "query"]},
            {"kind": "fetch", "description": f"Read a registry page (JSON) as path = value lines. Pages: {pages} "
                                             "(NAME is the package, or owner/name). Give a path (keys joined by /) to read the fields "
                                             "under it, such as info/license or time/1.2.3.",
             "arguments": {"url": "the page", "path": "optional: keys joined by /"}, "required": ["url"]},
            {"kind": "answer", "description": "Give the final answer: the value exactly as the registry gives it, or yes or no.",
             "arguments": {"value": "the answer", "confidence": "how sure you are, from 0 to 1"}, "required": ["value", "confidence"]},
            {"kind": "hand_off", "description": "Hand the question to someone else when the registries cannot answer it.",
             "arguments": {"reason": "why"}, "required": ["reason"]},
        ]

    def reset(self, case: dict, seed: int = 0) -> list[dict]:
        self.case, self.done, self.steps = case, False, 0
        self.state = {"answer": None, "handed_off": None, "refused": [], "proposed": [], "read": []}
        return question_claims(case)

    def _note(self, prop: str, value) -> list[dict]:
        return [claim("environment", prop, value, "environment", None)]

    def step(self, action: dict):
        if self.done:
            raise RuntimeError("the episode has ended: reset first")
        self.steps += 1
        kind = action.get("kind") if isinstance(action, dict) else None
        gate = self.gates.get(kind)
        info, terminated = {}, False
        if gate is None or gate == "deny":
            why = "not an action here" if gate is None else "not allowed here"
            self.state["refused"].append({"action": action, "why": why})
            obs = self._note("refused", f"{kind!r} is {why}; the actions are {', '.join(k for k, g in self.gates.items() if g != 'deny')}")
            info["refused"] = why
        elif gate == "propose":
            self.state["proposed"].append(action)
            obs = self._note("proposed", f"{kind} is recorded for a person to accept, edit or ignore; it changes nothing until then")
        elif kind == "search":
            obs = self._search(str(action.get("registry") or ""), str(action.get("query") or ""))
        elif kind == "fetch":
            obs = self._fetch(str(action.get("url") or ""), action.get("path"))
        elif kind == "answer":
            self.state["answer"] = str(action.get("value") if action.get("value") is not None else "").strip()
            obs, terminated = self._note("closed", "answered"), True
        elif kind == "hand_off":
            self.state["handed_off"] = str(action.get("reason") or "").strip() or "no reason given"
            obs, terminated, info["escalated"] = self._note("closed", "handed off"), True, True
        else:            # ask reaches the environment only when no such handler exists (the step loop resolves the rest)
            self.state["refused"].append({"action": action, "why": "no such handler"})
            obs, info["refused"] = self._note("refused", f"no handler {action.get('handler')!r} to ask"), "no such handler"
        truncated = not terminated and self.steps >= self.max_steps
        self.done = terminated or truncated
        return obs, None, terminated, truncated, info

    def _registry(self, name: str) -> str | None:
        return ALIASES.get(re.sub(r"[^a-z]", "", name.lower()))

    def _search(self, registry: str, query: str) -> list[dict]:
        reg = self._registry(registry)
        if reg not in self.pages:
            return self._note("refused", f"no registry {registry!r}; the registries are {', '.join(self.pages)}")
        tpl = self.pages[reg]["search"]
        if not tpl:
            return self._note("no search", f"{reg} has no search; fetch its page: {self.pages[reg]['page']}")
        url = re.sub(r"=N\b", "=5", tpl.replace("QUERY", urllib.parse.quote(query.strip())))
        entry = self._read(url)
        return entry if isinstance(entry, list) else hit_claims(reg, entry, self.pages)

    def _fetch(self, url: str, path) -> list[dict]:
        url = url.strip()
        for pattern, api in WEB:
            m = re.match(pattern, url)
            if m:
                url = api.format(m.group(1))
                break
        hosts = {urllib.parse.urlsplit(p[k].replace("NAME", "x").replace("QUERY", "x")).hostname
                 for p in self.pages.values() for k in ("search", "page") if p[k]}
        if urllib.parse.urlsplit(url).hostname not in hosts:
            return self._note("refused", f"{url!r} is not a registry page this environment reads ({', '.join(sorted(hosts))})")
        entry = self._read(url)
        return entry if isinstance(entry, list) else page_claims(entry, path if isinstance(path, str) else None, self.view)

    def _read(self, url: str):
        entry = self.record.get(url)
        self.state["read"].append(url)
        if entry is None:
            return [claim(url, "not recorded", "this page is not in the record this run replays", url, None)]
        if entry["status"] != 200:
            return [claim(url, "status", f"{entry['status']}: {cut(entry['body'], 200)}", url, entry["read_at"])]
        return entry

    def final(self) -> dict:
        """The state the outcome is read from: the answer given (or the hand-off), and what was read and refused."""
        return {"answer": self.state["answer"], "handed_off": self.state["handed_off"], "read": list(self.state["read"]),
                "refused": len(self.state["refused"]), "proposed": len(self.state["proposed"])}


def make(record: Record | None = None, spec: dict = SPEC) -> Lookups:
    return Lookups(record or Record(None, network=False), spec)
