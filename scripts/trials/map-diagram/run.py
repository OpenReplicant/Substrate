"""Draw each case with each candidate in headless Chromium under the UI's CSP, and print one line per candidate
and case: whether it drew, CSP violations, overlapping node boxes, time to draw, the bytes a page loads. Screenshots
and results.txt go to .state/trials/map-diagram/. Runs in the pinned Playwright image, with no network:

    scripts/trials/map-diagram/run.sh
"""
import http.server, json, sys, threading
from itertools import combinations
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
STATE = HERE.parents[2] / ".state/trials/map-diagram"
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
       "frame-ancestors 'self'; object-src 'none'; base-uri 'none'; form-action 'self'")   # deploy/caddy/Caddyfile L39
LIBS = {"cytoscape": ["cytoscape/cytoscape.min.js", "cytoscape-dagre/cytoscape-dagre.min.js"],
        "vis-network": ["vis-network/vis-network.min.js"], "g6": ["g6/g6.min.js"]}
CASES = ["substrate", "wide"]


class Handler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        p = path.split("?")[0].lstrip("/")
        base = STATE if p.split("/")[0] in ("vendor", "cases") else HERE / "web"
        return str(base / p)

    def end_headers(self):
        self.send_header("Content-Security-Policy", CSP)
        super().end_headers()

    def log_message(self, *a):
        pass


def overlaps(boxes, pad=1.0):
    return sum(1 for a, b in combinations(boxes, 2)
               if a["x1"] + pad < b["x2"] and b["x1"] + pad < a["x2"] and a["y1"] + pad < b["y2"] and b["y1"] + pad < a["y2"])


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{srv.server_port}"
lines = []
with sync_playwright() as pw:
    browser = pw.chromium.launch()
    for lib, files in LIBS.items():
        size = sum((STATE / "vendor" / f).stat().st_size for f in files)
        for case in CASES:
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            errors = []
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"{url}/{lib}.html?case={case}")
            r = None                                   # polled from here: wait_for_function evaluates a string, which the CSP refuses
            for _ in range(600):
                r = page.evaluate("() => window.__result")
                if r:
                    break
                page.wait_for_timeout(100)
            r = r or {"ok": False, "error": "no result in 60 s", "violations": []}
            page.wait_for_timeout(300)
            page.screenshot(path=str(STATE / f"{lib}-{case}.png"))
            page.close()
            line = (f"{lib:12} {case:10} drew={r['ok']} csp_violations={len(r['violations'])} "
                    f"overlaps={overlaps(r['boxes']) if r['ok'] else '-'} ms={r.get('ms', '-')} js_bytes={size}"
                    + ("" if r["ok"] else f" error={r['error'][:200]!r}")
                    + (f" violated={sorted(set(r['violations']))[:3]}" if r["violations"] else "")
                    + (f" console_errors={len(errors)} first={errors[0][:160]!r}" if errors else ""))
            print(line, flush=True)
            lines.append(line)
    browser.close()
(STATE / "results.txt").write_text("\n".join(lines) + "\n")
