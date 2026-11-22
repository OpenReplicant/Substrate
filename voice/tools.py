"""The fast layer's quick tools (S-171): what the voice model does itself, in one step, without the worker.

Each returns a short text for the model to read (the tool result), never raises for a bad argument (it says what was
wrong instead), and is quick: a file, a sum, one HTTP call with a short timeout. Multi-step work is the worker's
(`delegate`). Notes live in the worker's workspace (notes/<name>.txt, as the example plan writes them), so both
read the same ones. Reminders are records (the voice head keeps them in the environment and says them when due).
"""
from __future__ import annotations

import ast
import datetime as dt
import json
import operator
import re
import urllib.parse
import urllib.request
from pathlib import Path

UA = "substrate-voice/0.1 (local assistant)"        # Wikimedia asks for a descriptive User-Agent; nothing about the owner
MAX_RESULT = 1200


def note_name(text: str) -> str:
    """A file name for a note: its first few words, lower case, hyphenated (the example plan's [\\w-]+)."""
    words = re.findall(r"[a-z0-9]+", text.lower())[:5]
    return "-".join(words) or "note"


def save_note(root: str, text: str) -> str:
    text = (text or "").strip()
    if not text:
        return "error: the note is empty"
    d = Path(root) / "notes"
    d.mkdir(parents=True, exist_ok=True)
    base, n = note_name(text), 1
    f = d / f"{base}.txt"
    while f.exists():
        n += 1
        f = d / f"{base}-{n}.txt"
    f.write_text(text + "\n", encoding="utf-8")
    return f"saved as notes/{f.name}"


def read_notes(root: str, query: str = "") -> str:
    """The notes, newest first; with a query, only those containing one of its words."""
    d = Path(root) / "notes"
    files = sorted(d.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True) if d.is_dir() else []
    words = [w for w in re.findall(r"[a-z0-9]+", (query or "").lower()) if len(w) > 2]
    out = []
    for f in files:
        body = f.read_text(encoding="utf-8", errors="replace").strip()
        if words and not any(w in (f.stem + " " + body).lower() for w in words):
            continue
        out.append(f"{f.stem}: {body[:200]}")
    if not out:
        return "no notes" + (f" about {query}" if words else "")
    return "\n".join(out)[:MAX_RESULT]


def parse_when(when: str, now: dt.datetime) -> dt.datetime | None:
    """An ISO 8601 date-time (the model is given the current time), or 'in N minutes|hours|days'."""
    when = (when or "").strip()
    m = re.fullmatch(r"in (\d+) (minute|hour|day)s?", when.lower())
    if m:
        return now + dt.timedelta(**{m.group(2) + "s": int(m.group(1))})
    try:
        t = dt.datetime.fromisoformat(when.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=now.tzinfo)


def remind(text: str, when: str, now: dt.datetime) -> tuple[str, dict | None]:
    """(the result for the model, the reminder to keep or None)."""
    text = (text or "").strip()
    t = parse_when(when, now)
    if not text:
        return "error: the reminder has no text", None
    if t is None:
        return f"error: could not read the time {when!r}; give it as YYYY-MM-DDTHH:MM or 'in N minutes'", None
    if t <= now:
        return f"error: {t:%A %H:%M} has passed", None
    return f"reminder set for {t:%A %-d %B at %H:%M}", {"text": text, "due": t.isoformat()}


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos}


def calculate(expression: str) -> str:
    """Arithmetic only: numbers, + - * / // % ** and brackets (no names, no calls)."""
    def ev(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Pow) and abs(b) > 100:
                raise ValueError("exponent too large")
            return _OPS[type(n.op)](a, b)
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.operand))
        raise ValueError("only numbers and + - * / // % ** ( )")
    try:
        v = ev(ast.parse((expression or "").replace("^", "**").replace("×", "*").replace("÷", "/"), mode="eval").body)
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError) as e:
        return f"error: {e}"
    if isinstance(v, float):
        v = round(v, 10)
        v = int(v) if v.is_integer() else v
    return f"{expression} = {v}"


def _get(url: str, timeout: float = 6) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def lookup(topic: str, get=_get) -> str:
    """Wikipedia's summary of the best-matching article (English), with its title."""
    topic = (topic or "").strip()
    if not topic:
        return "error: nothing to look up"
    try:
        hits = get("https://en.wikipedia.org/w/rest.php/v1/search/page?" + urllib.parse.urlencode({"q": topic, "limit": 1})).get("pages") or []
        if not hits:
            return f"Wikipedia has no article for {topic!r}"
        s = get("https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(hits[0]["key"], safe=""))
    except (OSError, ValueError, KeyError) as e:
        return f"error: Wikipedia did not answer ({type(e).__name__})"
    return f"Wikipedia, {s.get('title', hits[0].get('title'))}: {(s.get('extract') or '').strip()}"[:MAX_RESULT]


def search(query: str, base: str, get=_get) -> str:
    """The top results from the local SearXNG (title, a snippet, the site), for the model to answer from."""
    query = (query or "").strip()
    if not query:
        return "error: nothing to search for"
    if not base:
        return "error: no search engine is set up (SEARCH_URL)"
    try:
        res = get(f"{base.rstrip('/')}/search?" + urllib.parse.urlencode({"q": query, "format": "json"}), timeout=8).get("results") or []
    except (OSError, ValueError) as e:
        return f"error: the search did not answer ({type(e).__name__})"
    if not res:
        return f"no results for {query!r}"
    out = []
    for r in res[:4]:
        site = urllib.parse.urlparse(r.get("url") or "").netloc
        out.append(f"- {(r.get('title') or '').strip()} ({site}): {(r.get('content') or '').strip()[:220]}")
    return "\n".join(out)[:MAX_RESULT]
