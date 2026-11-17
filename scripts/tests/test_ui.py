"""The UI (S-140), against a throwaway database it drops after (ADMIN_URL from scripts/test.sh). It should:
- serve its vendored files as recorded in ui/static/vendor/VENDOR.md (SHA-256), with their licences beside them
- answer search, wholes, an entity's page and a map (nodes by kind, edges by kind) from the store
- send its CSP (scripts and styles from itself only) on every response, and its page needs nothing more: no inline
  script, no inline style, nothing loaded from elsewhere
- serve nothing outside ui/static, and refuse ids that are not entity ids
- not write: its session is read-only

    scripts/test.sh scripts/tests/test_ui.py
"""
import hashlib
import json
import os
import re
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import store  # noqa: E402
from store import Store, person  # noqa: E402
from ui import server  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print(("ok  " if ok else "FAIL"), name, "" if ok else detail)


def get(base, path):
    try:
        with urllib.request.urlopen(base + path, timeout=10) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def main():
    admin = os.environ["ADMIN_URL"]
    name = f"ui_test_{os.getpid()}"
    with psycopg.connect(admin, autocommit=True) as a:
        a.execute(f"create database {name}")
    url = admin.rsplit("/", 1)[0] + "/" + name
    try:
        with psycopg.connect(url, autocommit=True) as c:
            run(c, url)
    finally:
        with psycopg.connect(admin, autocommit=True) as a:
            a.execute(f"drop database {name} with (force)")
    print(f"{sum(checks)}/{len(checks)} checks passed")
    sys.exit(0 if all(checks) else 1)


def vendored():
    static = ROOT / "ui/static"
    rows = re.findall(r"^\| `([^`]+)` \|.*\| `([0-9a-f]{64})` \|$", (static / "vendor/VENDOR.md").read_text(), re.M)
    check("VENDOR.md lists the vendored files", len(rows) == 2, rows)
    for f, sha in rows:
        p = static / "vendor" / f
        check(f"{f} is the file recorded", p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest() == sha)
        check(f"{f} has its licence beside it", (p.parent / "LICENSE").is_file())
    html = (static / "index.html").read_text()
    check("the page has no inline script", not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html))
    check("the page has no inline style", "<style" not in html and " style=" not in html)
    check("the page loads nothing from elsewhere", not re.search(r"(src|href)=\"(https?:)?//", html))
    js = (static / "app.js").read_text()
    check("the script never writes HTML", "innerHTML" not in js and "insertAdjacentHTML" not in js and "document.write" not in js)


def run(c, url):
    vendored()
    store.migrate(c)
    s = Store(c, actor="test")
    me = person("tester")
    with s.edit("a bicycle"):
        bike = s.item("bicycle", description="a whole")
        drive = s.item("drivetrain role")
        s.say(drive, s.id("instance-of"), s.id("role"), by=me)
        fit = s.item("1/2 x 3/32 inch chain fitting")
        s.say(fit, s.id("instance-of"), s.id("interface"), by=me)
        s.say(drive, s.id("requires-interface"), fit, by=me)
        chain, other = s.item("derailleur chain"), s.item("single-speed chain")
        for x in (chain, other):
            s.say(x, s.id("provides-interface"), fit, by=me)
        s.say(bike, s.id("has-part"), chain, by=me, qualifiers=[(s.id("object-has-role"), drive)])
    s.render(bike)

    srv = server.serve("127.0.0.1", 0, url)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    try:
        st, h, body = get(base, "/")
        check("the page is served", st == 200 and b"app.js" in body, st)
        for path in ("/", "/static/app.js", "/api/wholes", "/nope"):
            st, h, _ = get(base, path)
            csp = h.get("Content-Security-Policy", "")
            check(f"{path} carries the CSP", "script-src 'self'" in csp and "style-src 'self'" in csp and "unsafe" not in csp, csp)
        st, h, body = get(base, "/static/vendor/cytoscape/cytoscape.min.js")
        check("vendored scripts are served as JavaScript", st == 200 and "javascript" in h.get("Content-Type", ""), (st, h.get("Content-Type")))
        wholes = json.loads(get(base, "/api/wholes")[2])
        check("wholes: what has parts", [w["id"] for w in wholes] == [bike], wholes)
        m = json.loads(get(base, f"/api/map/{bike}")[2])
        kinds = {n["id"]: n["kind"] for n in m["nodes"]}
        check("a map's nodes by kind", kinds == {bike: "whole", chain: "part", drive: "role", fit: "interface", other: "candidate"}, kinds)
        edges = {(e["source"], e["target"], e["kind"]) for e in m["edges"]}
        check("a map's edges by kind", {(bike, chain, "has-part"), (chain, drive, "plays"), (drive, fit, "requires"),
                                        (chain, fit, "provides"), (other, drive, "could-fill")} <= edges, edges)
        e = json.loads(get(base, f"/api/entity/{bike}")[2])
        check("an entity's page and whether it has a map", e["has_map"] and e["markdown"].startswith(f"# bicycle ({bike})"), e)
        hits = json.loads(get(base, "/api/search?q=chain")[2])
        check("search finds", chain in [x["id"] for x in hits], hits)
        check("an unknown entity is 404", get(base, "/api/entity/Q999999")[0] == 404)
        check("an id that is not one is 404", get(base, "/api/map/x;drop")[0] == 404)
        for path in ("/static/../server.py", "/static/%2e%2e/server.py", "/static/vendor/../../server.py"):
            check(f"nothing outside ui/static: {path}", get(base, path)[0] == 404)
        st = server.Store(url)
        try:
            st.query("select store.new_entity('item', 'x')")
            check("its session is read-only", False)
        except psycopg.Error as err:
            check("its session is read-only", "read-only" in str(err), err)
    finally:
        srv.shutdown()


if __name__ == "__main__":
    main()
