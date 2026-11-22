"""Records every outbound request that is routed to it (HTTP(S)_PROXY) and refuses it with 502.
Anything in the log is a network call a candidate made beyond the stub on 127.0.0.1."""
import os, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOG = os.environ.get("PROXY_LOG", "proxy_hits.log")


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _hit(self):
        with open(LOG, "a") as f:
            f.write("%s %s\n" % (self.command, self.path if self.command != "CONNECT" else self.path))
        self.send_response(502)
        self.send_header("content-length", "0")
        self.end_headers()

    do_GET = do_POST = do_CONNECT = do_PUT = _hit


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
