"""A stdio MCP server for the router trial (S-204): two tools, one that only reads (echo) and one that changes the world
(write_note, annotated destructiveHint, so a router's gate should hold it). Standard library only; MCP 2025-11-25,
newline-delimited JSON-RPC on stdin and stdout."""
import json, sys

TOOLS = [
    {"name": "echo", "description": "Say the text back.", "annotations": {"readOnlyHint": True},
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
    {"name": "write_note", "description": "Write a note (changes the world).", "annotations": {"destructiveHint": True},
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
]
notes = []
for line in sys.stdin:
    try:
        m = json.loads(line)
    except ValueError:
        continue
    if "id" not in m:
        continue
    meth, p = m.get("method"), m.get("params") or {}
    if meth == "initialize":
        r = {"protocolVersion": p.get("protocolVersion", "2025-11-25"), "capabilities": {"tools": {}},
             "serverInfo": {"name": "trial-tools", "version": "0"}}
    elif meth == "tools/list":
        r = {"tools": TOOLS}
    elif meth == "tools/call":
        a = p.get("arguments") or {}
        if p.get("name") == "echo":
            r = {"content": [{"type": "text", "text": a.get("text", "")}]}
        elif p.get("name") == "write_note":
            notes.append(a.get("text", ""))
            r = {"content": [{"type": "text", "text": f"note {len(notes)} written"}]}
        else:
            r = {"content": [{"type": "text", "text": "no such tool"}], "isError": True}
    elif meth == "ping":
        r = {}
    else:
        print(json.dumps({"jsonrpc": "2.0", "id": m["id"], "error": {"code": -32601, "message": "method not found"}}), flush=True)
        continue
    print(json.dumps({"jsonrpc": "2.0", "id": m["id"], "result": r}), flush=True)
