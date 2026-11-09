"""Workbench over MCP, for agents (BRIEF.md section 5). Streamable HTTP with plain JSON responses: no session, no
server-sent stream. Every tool forwards the agent's own token to PostgREST, so an agent reads and writes under
the same rules as a person: its role limits it, the triggers record its claims under its name.

The protocol parts used are the base ones: initialize, notifications/initialized, ping, tools/list, tools/call.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

PROTOCOL = "2025-06-18"
SUPPORTED = {"2025-06-18", "2025-03-26"}


class ToolError(Exception):
    pass


class Tools:
    def __init__(self, token: str, who: dict, postgrest: str, queue, extractors):
        self.token, self.who, self.base, self.queue, self.extractors = token, who, postgrest.rstrip("/"), queue, extractors

    def rest(self, method: str, path: str, query: dict | None = None, body=None, prefer: str | None = None):
        url = f"{self.base}/{path}" + ("?" + urllib.parse.urlencode(query) if query else "")
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if prefer:
            headers["Prefer"] = prefer
        req = urllib.request.Request(url, method=method, headers=headers,
                                     data=None if body is None else json.dumps(body).encode())
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                text = r.read().decode()
                return json.loads(text) if text else None
        except urllib.error.HTTPError as e:
            detail = e.read().decode()
            try:
                detail = json.loads(detail).get("message", detail)
            except ValueError:
                pass
            raise ToolError(f"{e.code}: {detail}") from None

    # ---------------------------------------------------------------- the tools
    def search(self, q: str, limit: int = 10):
        hits = self.rest("POST", "rpc/search", body={"q": q, "lim": limit})
        best = {}
        for h in hits:
            k = (h["type"], h["id"])
            if k not in best or best[k]["rank"] < h["rank"]:
                best[k] = h
        return sorted(best.values(), key=lambda h: -h["rank"])[:limit]

    def list_types(self):
        return [{"id": t["id"], "label": t["label"], "plugin": t["plugin"],
                 "fields": sorted((t["schema"] or {}).get("properties", {}))} for t in self.rest("GET", "content_types")]

    def list_items(self, type: str, contains: str = "", limit: int = 25):
        q = {"select": "id,slug,title,updated_at,updated_by", "order": "updated_at.desc", "limit": str(limit)}
        if contains:
            q["or"] = f"(title.ilike.*{contains}*,slug.ilike.*{contains}*)"
        return self.rest("GET", type, q)

    def _find(self, type: str, ref: str):
        key = "id" if len(ref) == 36 and ref.count("-") == 4 else "slug"
        rows = self.rest("GET", type, {key: f"eq.{ref}"})
        if not rows:
            raise ToolError(f"no {type} {ref}")
        return rows[0]

    def get_item(self, type: str, ref: str):
        item = self._find(type, ref)
        claims = self.rest("GET", "claims", {"subject_id": f"eq.{item['id']}", "status": "in.(current,disputed)",
                                              "select": "field,value,author,status,observed_at,quote,source_id",
                                              "order": "field.asc,observed_at.desc"})
        return {"item": item, "claims": claims}

    def save_item(self, type: str, slug: str, fields: dict, title: str | None = None):
        body = {k: v for k, v in (fields or {}).items() if k not in ("id", "created_at", "updated_at", "created_by", "updated_by")}
        if title:
            body["title"] = title
        rows = self.rest("GET", type, {"slug": f"eq.{slug}", "select": "id"})
        if rows:
            out = self.rest("PATCH", type, {"id": f"eq.{rows[0]['id']}"}, body, "return=representation")
        else:
            body.setdefault("title", slug)
            out = self.rest("POST", type, None, {"slug": slug, **body}, "return=representation")
        return out[0] if out else None

    def retire_item(self, type: str, ref: str, note: str = ""):
        item = self._find(type, ref)
        return self.rest("POST", "rpc/retire", body={"type": type, "id": item["id"], "note": note or None})

    def restore_item(self, type: str, ref: str):
        item = self._find(type, ref)
        return self.rest("POST", "rpc/restore", body={"type": type, "id": item["id"]})

    def claims(self, type: str, ref: str, field: str = ""):
        item = self._find(type, ref)
        q = {"subject_id": f"eq.{item['id']}", "order": "observed_at.desc", "limit": "100",
             "select": "field,value,author,status,observed_at,quote,span,source_id,run_id"}
        if field:
            q["field"] = f"eq.{field}"
        return self.rest("GET", "claims", q)

    def open_decisions(self, limit: int = 25):
        return self.rest("GET", "decisions", {"status": "eq.open", "order": "created_at.desc", "limit": str(limit),
                                              "select": "id,kind,subject,raised_by,created_at"})

    def decide(self, id: str, approve: bool, note: str = ""):
        return self.rest("POST", "rpc/decide", body={"id": id, "approve": approve, "note": note or None})

    def list_extractors(self):
        return self.extractors()

    def run_extractor(self, key: str):
        try:
            return {"queued": self.queue(key, {})}
        except (PermissionError, KeyError) as e:
            raise ToolError(str(e)) from None


S = {"type": "string"}
TOOLS = [
    ("search", "Search every content type and every claim's quoted source for words (any word, as a prefix).",
     {"q": S, "limit": {"type": "integer", "default": 10}}, ["q"]),
    ("list_types", "The content types: each a table of items, with its fields.", {}, []),
    ("list_items", "Items of one type, newest change first; optionally only those whose title or slug contains text.",
     {"type": S, "contains": S, "limit": {"type": "integer", "default": 25}}, ["type"]),
    ("get_item", "One item (by id or slug) with the current claims behind each of its values: who said it, when, the quote.",
     {"type": S, "ref": S}, ["type", "ref"]),
    ("save_item", "Create or change an item by slug. Every value written becomes a claim attributed to you. Needs the editor role.",
     {"type": S, "slug": S, "fields": {"type": "object"}, "title": S}, ["type", "slug", "fields"]),
    ("retire_item", "Retire an item (nothing is deleted): every current claim behind it is retracted, and the retirement, "
     "with your note, is a claim of yours. restore_item undoes it. Needs the editor role.",
     {"type": S, "ref": S, "note": S}, ["type", "ref"]),
    ("restore_item", "Undo a retirement: the claims it retracted are current again, except where something newer was written.",
     {"type": S, "ref": S}, ["type", "ref"]),
    ("claims", "Every claim about an item (current, superseded, retracted), newest first; optionally one field.",
     {"type": S, "ref": S, "field": S}, ["type", "ref"]),
    ("open_decisions", "Decisions waiting for a person or an agent with the right role: gaps, disputes, proposals.",
     {"limit": {"type": "integer", "default": 25}}, []),
    ("decide", "Approve or decline an open decision, with a note. Needs the editor role.",
     {"id": S, "approve": {"type": "boolean"}, "note": S}, ["id", "approve"]),
    ("list_extractors", "The extractors plugins provide.", {}, []),
    ("run_extractor", "Queue an extractor run. Needs the editor role.", {"key": S}, ["key"]),
]


def handle(msg: dict, tools: Tools) -> dict | None:
    """One JSON-RPC message; None for a notification."""
    method, mid = msg.get("method"), msg.get("id")
    if mid is None:
        return None
    ok = lambda result: {"jsonrpc": "2.0", "id": mid, "result": result}  # noqa: E731
    if method == "initialize":
        asked = (msg.get("params") or {}).get("protocolVersion")
        return ok({"protocolVersion": asked if asked in SUPPORTED else PROTOCOL,
                   "capabilities": {"tools": {"listChanged": False}},
                   "serverInfo": {"name": "workbench", "version": "0.1.0"},
                   "instructions": "Workbench: typed items whose every value has claims behind it (who said it, when, from "
                                   "which source). Search, read with get_item, and write with save_item; your writes are "
                                   f"attributed to {tools.who.get('name')}."})
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": [{"name": n, "description": d, "inputSchema": {"type": "object", "properties": p, "required": r}}
                             for n, d, p, r in TOOLS]})
    if method == "tools/call":
        params = msg.get("params") or {}
        name, args = params.get("name"), params.get("arguments") or {}
        if name not in {t[0] for t in TOOLS}:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"no tool {name}"}}
        try:
            result = getattr(tools, name)(**args)
            return ok({"content": [{"type": "text", "text": json.dumps(result, indent=1, default=str)}], "isError": False})
        except (ToolError, TypeError) as e:
            return ok({"content": [{"type": "text", "text": str(e)}], "isError": True})
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"no method {method}"}}
