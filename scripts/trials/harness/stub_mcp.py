"""A stub MCP server over stdio, standard library only (any image with python3 runs it): one tool, `add`, and a log of
every call in STUB_MCP_LOG. MCP's stdio transport is JSON-RPC 2.0, one message per line."""
import json
import os
import sys

LOG = os.environ.get("STUB_MCP_LOG", "/tmp/stub_mcp.log")
TOOLS = [{"name": "add", "description": "Add two numbers and return the sum",
          "inputSchema": {"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "number"}}, "required": ["a", "b"]}}]


def reply(i, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": i}
    msg.update({"error": error} if error else {"result": result})
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


for line in sys.stdin:
    try:
        m = json.loads(line)
    except ValueError:
        continue
    method, i = m.get("method"), m.get("id")
    if i is None:                                          # a notification (e.g. notifications/initialized)
        continue
    if method == "initialize":
        reply(i, {"protocolVersion": (m.get("params") or {}).get("protocolVersion", "2025-06-18"),
                  "capabilities": {"tools": {}}, "serverInfo": {"name": "stub", "version": "0.1"}})
    elif method == "tools/list":
        reply(i, {"tools": TOOLS})
    elif method == "tools/call":
        p = m.get("params") or {}
        args = p.get("arguments") or {}
        with open(LOG, "a") as f:
            f.write(json.dumps({"tool": p.get("name"), "arguments": args}) + "\n")
        if p.get("name") != "add":
            reply(i, error={"code": -32602, "message": "no such tool"})
        else:
            total = (args.get("a") or 0) + (args.get("b") or 0)
            reply(i, {"content": [{"type": "text", "text": str(total)}], "isError": False})
    elif method == "ping":
        reply(i, {})
    else:
        reply(i, error={"code": -32601, "message": f"method not found: {method}"})
