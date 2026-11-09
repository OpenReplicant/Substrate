"""Interview transcripts (INTERVIEW.md): what a person said about a system, kept word for word, and the statements
taken from it, each quoting the person.

A transcript is Markdown in .state/interviews/<system>/<name>.md (gitignored: what someone says about their system is
theirs). Front matter names the system, the person and the interviewer; each turn is a `## ` heading followed by
lines `**<name>:** words`, and a statement block (a fenced yaml list under `## Statements`) says what was taken from
it:

    ---
    system: rig
    person: pete
    interviewer: claude-code
    date: 2026-11-09
    scope: this machine's Claude Code setup; nothing in ~/Documents
    ---
    ## 1. What it is for
    **claude-code:** What is this machine for?
    **pete:** It's my dev box. I build substrate on it.

    ## Statements
    ```yaml
    - {item: component:rig, field: description, value: "The owner's dev box, where substrate is built",
       quote: "It's my dev box. I build substrate on it.", turn: 1}
    ```

`parse` reads one; `check` says which statements stand: a statement stands only if its quote is, word for word
(whitespace aside), in what the person said in that turn. Anything else is refused, with the reason.
"""
from __future__ import annotations

import re

import yaml

SPEAKER = re.compile(r"^\*\*(?P<name>[^*:]+):\*\*\s?(?P<text>.*)$")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def parse(text: str) -> dict:
    """{meta, turns: {id: {title, line, said: [(name, text, line)]}}, statements: [(statement, line)], problems}"""
    lines = text.splitlines()
    meta, start, problems = {}, 0, []
    if lines and lines[0].strip() == "---":
        end = next((i for i, l in enumerate(lines[1:], 1) if l.strip() == "---"), None)
        if end is None:
            return {"meta": {}, "turns": {}, "statements": [], "problems": ["front matter is not closed with ---"]}
        meta = yaml.safe_load("\n".join(lines[1:end])) or {}
        start = end + 1
    turns, statements, current, in_statements, block, block_at = {}, [], None, False, None, 0
    for n, line in enumerate(lines[start:], start + 1):
        if block is not None:
            if line.strip().startswith("```"):
                try:
                    items = yaml.safe_load("\n".join(block)) or []
                except yaml.YAMLError as e:
                    problems.append(f"line {block_at}: the statements are not valid YAML ({e.__class__.__name__})")
                    items = []
                statements += [(s, block_at) for s in (items if isinstance(items, list) else [items])]
                block = None
            else:
                block.append(line)
            continue
        if line.startswith("## "):
            title = line[3:].strip()
            in_statements = title.lower() == "statements"
            if not in_statements:
                tid = (re.match(r"^(\w+)[.:)]?\s", title + " ") or [None, title])[1]
                current = turns.setdefault(str(tid), {"title": title, "line": n, "said": []})
            continue
        if in_statements and line.strip().startswith("```"):
            block, block_at = [], n
            continue
        m = SPEAKER.match(line)
        if m and current is not None:
            current["said"].append([m["name"].strip(), m["text"], n])
        elif current is not None and current["said"] and line.strip():
            current["said"][-1][1] += "\n" + line        # a long answer goes on over several lines
    return {"meta": meta, "turns": turns, "statements": statements, "problems": problems}


def check(doc: dict) -> list[dict]:
    """Each statement with `ok` and, if refused, `why`; a standing one also carries the line its quote is on."""
    person = str(doc["meta"].get("person") or "")
    out = []
    for i, (s, at) in enumerate(doc["statements"], 1):
        r = {"statement": s, "line": at, "n": i, "ok": False}
        out.append(r)
        if not isinstance(s, dict) or not all(s.get(k) not in (None, "") for k in ("item", "field", "quote")) or "value" not in s:
            r["why"] = "a statement needs item, field, value and quote"
            continue
        if not person:
            r["why"] = "the transcript names no person (front matter: person)"
            continue
        turns = [doc["turns"][str(s["turn"])]] if s.get("turn") is not None and str(s["turn"]) in doc["turns"] else \
            list(doc["turns"].values()) if s.get("turn") is None else []
        if not turns:
            r["why"] = f"no turn {s['turn']} in the transcript"
            continue
        hit = next(((text, line) for t in turns for name, text, line in t["said"]
                    if name == person and _norm(str(s["quote"])) in _norm(text)), None)
        if not hit:
            r["why"] = f"{person} did not say that, word for word, in " + (f"turn {s['turn']}" if s.get("turn") is not None else "the transcript")
            continue
        r.update(ok=True, quote_line=hit[1])
    return out
