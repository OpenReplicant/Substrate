"""The store's agent tools over MCP (stdio).

    bin/in-tools python3 -m store.mcp          # .mcp.json starts it this way for Claude Code

Reading: search, read, expand, locate, path, alternatives, violations. Writing (S-139): create_item, say, deprecate. What a
client writes is a claim: its reference is the client as an interpreter (the name and version it gave at
initialize), it enters at normal rank, and only a person prefers it or deprecates someone else's. Properties
are not made here: they are governed (S-135), made by a migration or a person.

The database is STORE_URL, or the substrate database from .env. Speaks MCP 2025-11-25 (and 2025-06-18, if a
client asks for it): newline-delimited JSON-RPC on stdin and stdout, logs on stderr. Read 2026-11-17 at
modelcontextprotocol.io/specification/2025-11-25 (lifecycle, server/tools, transports).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import psycopg

from store import Store, interpreter

VERSIONS = ("2025-11-25", "2025-06-18")


def obj(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required}


S, I, B, A = {"type": "string"}, {"type": "integer"}, {"type": "boolean"}, {"type": "array"}
EVIDENCE = {"type": "object", "description": "the text this rests on: the source's URI (file:path, https://...), where in it "
            "(p3, L10-20) and the quoted text", "properties": {"source": S, "locator": S, "quote": S},
            "required": ["source", "locator", "quote"]}
TOOLS = [
    {"name": "search", "description": "Find entities by label, alias, key or the words on their pages. Returns ids "
     "(Q items, P properties) with labels and descriptions.", "inputSchema": obj({"query": S, "limit": I}, ["query"])},
    {"name": "read", "description": "Read an entity's page: its usable statements (preferred, else normal rank), "
     "qualifiers, numbered references and what is flagged. all_ranks shows deprecated ones too.",
     "inputSchema": obj({"id": S, "all_ranks": B}, ["id"])},
    {"name": "expand", "description": "One hop from an entity: its usable statements, and the statements whose value it is.",
     "inputSchema": obj({"id": S}, ["id"])},
    {"name": "locate", "description": "The evidence behind an entity's statements, or one statement (by its uuid): who "
     "stated it, the source and pinned text it rests on, whether that text has changed since, and a rule's premises.",
     "inputSchema": obj({"target": S}, ["target"])},
    {"name": "path", "description": "The shortest path from one entity to another along statements that are not "
     "deprecated, in their direction (has part, provides interface, ...).", "inputSchema": obj({"from": S, "to": S}, ["from", "to"])},
    {"name": "alternatives", "description": "What could fill a role: everything that provides every interface the role "
     "requires, and whether it fills the role now and in which whole.", "inputSchema": obj({"role": S}, ["role"])},
    {"name": "violations", "description": "Constraint violations (reported, never blocking): a property's values of the "
     "wrong class, a single-value property with several, a string off its format. For one entity, or all.",
     "inputSchema": obj({"id": S}, [])},
    {"name": "create_item", "description": "Make an item (a thing, part, role, interface, goal, catalog, candidate). "
     "Search first: it answers with similar items that already exist. instance_of is an id or key (role, interface, goal, "
     "catalog, or any class item).", "inputSchema": obj({"label": S, "description": S, "aliases": {**A, "items": S},
                                                         "instance_of": S, "evidence": EVIDENCE}, ["label"])},
    {"name": "say", "description": "State something about an entity: property (id or key, e.g. has-part), value in its "
     "datatype's form (an item's id or key; a string; a quantity {amount, unit, lower, upper}; a time '2026-11-17'; a "
     "URL), qualifiers [{property, value}], and the evidence it rests on. It enters at normal rank as your claim.",
     "inputSchema": obj({"subject": S, "property": S, "value": {}, "qualifiers": {**A, "items": obj({"property": S, "value": {}}, ["property", "value"])},
                         "evidence": EVIDENCE, "note": S}, ["subject", "property", "value"])},
    {"name": "deprecate", "description": "Deprecate a statement you made (by its uuid), saying why. Someone else's "
     "statements are reviewed by a person: say a contradicting one instead.", "inputSchema": obj({"statement": S, "reason": S}, ["statement", "reason"])},
]


def database_url() -> str:
    if os.environ.get("STORE_URL"):
        return os.environ["STORE_URL"]
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from db import DB, admin_url  # noqa: E402
    from gateway import settings  # noqa: E402
    return admin_url(settings(), DB)


class Server:
    def __init__(self):
        self.client = ("mcp-client", "unknown")
        self._s: Store | None = None

    @property
    def s(self) -> Store:
        if self._s is not None and self._s.c.closed:     # Postgres restarted under us: connect again
            self._s = None
        if self._s is None:
            conn = psycopg.connect(database_url(), autocommit=True)
            self._s = Store(conn, actor=f"{self.client[0]} {self.client[1]} (MCP)")
        return self._s

    def ref(self, s: Store, evidence: dict | None, note: str | None = None):
        span = s.read_span(evidence["source"], evidence["locator"], evidence["quote"])[0] if evidence else None
        return interpreter(self.client[0], self.client[1], span=span, note=note)

    def value(self, s: Store, prop: str, v):
        return s.resolve(v) if s.datatype(prop) in ("item", "property") and isinstance(v, str) else v

    def call(self, name: str, a: dict) -> str:
        s = self.s
        if name == "search":
            hits = s.search(a["query"], int(a.get("limit") or 10))
            return "\n".join(f"{h['id']}  {h['label']}" + (f": {h['description']}" if h["description"] else "") for h in hits) or "nothing found"
        if name == "read":
            return s.render(s.resolve(a["id"]), bool(a.get("all_ranks"))) or f"no entity {a['id']}"
        if name == "expand":
            e = s.resolve(a["id"])
            rows = s.expand(e)
            return "\n".join((f"{e} {r['property_label']} ({r['property']}) {r['value']}" if r["direction"] == "out"
                              else f"{r['value']} {r['property_label']} ({r['property']}) {e}")
                             + ("" if r["rank"] == "normal" else f" ({r['rank']})") for r in rows) or "no statements"
        if name == "locate":
            t = a["target"]
            found = s.locate(t if len(t) > 20 else s.resolve(t))
            return json.dumps(found, indent=1, default=str) if found else "no evidence found"
        if name == "path":
            steps = s.path(s.resolve(a["from"]), s.resolve(a["to"]))
            return " -> ".join((f"[{p['via_label']}] " if p["via_label"] else "") + f"{p['label']} ({p['entity']})" for p in steps) or "no path"
        if name == "alternatives":
            rows = s.alternatives(s.resolve(a["role"]))
            return "\n".join(f"{r['entity']}  {r['label']}" + (f"  (fills it now, in {r['in_whole']})" if r["fills_now"] else "")
                             for r in rows) or "nothing provides every interface this role requires (or it requires none)"
        if name == "violations":
            e = s.resolve(a["id"]) if a.get("id") else None
            rows = [v for v in s.violations() if e is None or v["subject"] == e]
            return "\n".join(f"{v['subject']} {v['property']} ({v['kind']}): {v['message']} [statement {v['statement']}]" for v in rows) or "none"
        if name == "create_item":
            similar = [h for h in s.search(a["label"], 5) if h["score"] >= 0.5]
            with s.edit(f"create {a['label']}"):
                q = s.item(a["label"], description=a.get("description"), aliases=a.get("aliases") or ())
                if a.get("instance_of"):
                    s.say(q, s.id("instance-of"), s.resolve(a["instance_of"]), by=self.ref(s, a.get("evidence")))
                elif a.get("evidence"):
                    raise KeyError("evidence goes with a statement: give instance_of, or say it with say")
            note = "".join(f"\nsimilar, already here: {h['id']} {h['label']}" for h in similar)
            return f"{q}{note}"
        if name == "say":
            subj, prop = s.resolve(a["subject"]), s.resolve(a["property"])
            quals = [(s.resolve(q["property"]), self.value(s, s.resolve(q["property"]), q["value"])) for q in a.get("qualifiers") or []]
            with s.edit(f"say {prop} on {subj}"):
                sid = s.say(subj, prop, self.value(s, prop, a["value"]), qualifiers=quals,
                            by=self.ref(s, a.get("evidence"), a.get("note")))
            return sid
        if name == "deprecate":
            st = a["statement"]
            others = s.c.execute("select count(*) from store.cites c join store.reference r on r.id = c.reference_id "
                                 "where c.statement_id = %s and not (r.by_kind = 'interpreter' and r.by_name = %s)",
                                 (st, self.client[0])).fetchone()[0]
            if others:
                raise PermissionError("someone else also stated this; a person reviews it. Say a contradicting statement instead.")
            s.rank(st, "deprecated", a["reason"])
            return f"deprecated {st}"
        raise KeyError(name)

    def handle(self, msg: dict) -> dict | None:
        mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
        if mid is None:                     # a notification (notifications/initialized and the like): no answer
            return None
        if method == "initialize":
            info = params.get("clientInfo") or {}
            self.client = (str(info.get("name") or "mcp-client"), str(info.get("version") or "unknown"))
            asked = params.get("protocolVersion")
            return {"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": asked if asked in VERSIONS else VERSIONS[0],
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "substrate-store", "version": "0.2.0"},
                "instructions": "Substrate's store: entities with statements, references and pinned spans (Wikibase's model). "
                                "search to find, read a page, expand to neighbours, locate the evidence, path and alternatives "
                                "over parts, roles and interfaces; create_item and say write your claims, with evidence."}}
        if method == "ping":
            return {"jsonrpc": "2.0", "id": mid, "result": {}}
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
        if method == "tools/call":
            name = params.get("name")
            if name not in {t["name"] for t in TOOLS}:
                return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"unknown tool: {name}"}}
            try:
                try:
                    text, err = self.call(name, params.get("arguments") or {}), False
                except psycopg.OperationalError:
                    # the connection was lost (a restarted Postgres), so whatever this call began was rolled back:
                    # connect again and run it once more
                    self._s = None
                    text, err = self.call(name, params.get("arguments") or {}), False
            except (KeyError, ValueError, PermissionError, psycopg.Error) as e:
                text, err = f"{type(e).__name__}: {e}", True
            return {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": text}], "isError": err}}
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"no method {method}"}}


def main() -> None:
    server = Server()
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            out = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "not JSON"}}
        else:
            out = server.handle(msg)
        if out is not None:
            sys.stdout.write(json.dumps(out) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
