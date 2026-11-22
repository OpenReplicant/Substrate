"""Stub OpenAI-compatible chat server. First request (no tool message yet) answers with a tool call to
`add`; once a tool message is present it answers "The answer is <tool result>". Every request is appended
to the call log (path in STUB_LOG), so the trial counts model calls from the server's side."""
import json, os, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOG = os.environ.get("STUB_LOG", "stub_calls.jsonl")


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))))
        msgs = body.get("messages", [])
        tool_msgs = [m for m in msgs if m.get("role") == "tool"]
        with open(LOG, "a") as f:
            f.write(json.dumps({"path": self.path, "auth": self.headers.get("authorization"),
                                "model": body.get("model"), "tools": [t["function"]["name"] for t in body.get("tools", [])],
                                "n_messages": len(msgs), "stream": bool(body.get("stream"))}) + "\n")
        if tool_msgs:
            msg = {"role": "assistant", "content": "The answer is %s." % _text(tool_msgs[-1]["content"])}
            fin = "stop"
        else:
            msg = {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "add", "arguments": json.dumps({"a": 2, "b": 3})}}]}
            fin = "tool_calls"
        out = {"id": "chatcmpl-stub", "object": "chat.completion", "created": int(time.time()), "model": body.get("model"),
               "choices": [{"index": 0, "message": msg, "finish_reason": fin}],
               "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _text(c):
    if isinstance(c, list):
        return "".join(p.get("text", "") for p in c)
    return str(c)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
