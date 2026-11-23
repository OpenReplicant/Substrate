"""The UI (S-140, S-154, S-156), against throwaway databases it drops after (ADMIN_URL from scripts/test.sh): a store
in the old schema (scripts/tests/oldschema, the exporter's fixture) with a bicycle's map, exported into a throwaway
Knowledge Kernel (scripts/tests/kernelfx.py), and the UI on that kernel. It should:
- serve its vendored files as recorded in ui/static/vendor/VENDOR.md (SHA-256), with their licences beside them
- answer search, wholes, an entity's page and a map (nodes by kind, edges by kind) 
- send its CSP (scripts and styles from itself only) on every response, and its page needs nothing more: no inline
  script, no inline style, nothing loaded from elsewhere
- serve nothing outside ui/static, and refuse ids that are not entity ids
- not write: its session is read-only; on the kernel it is the read model's role, under the kernel's row-level security
  (a claim in a scope it is not cleared for is in no answer)

    scripts/test.sh scripts/tests/test_ui.py
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kernelfx  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent / "oldschema"))
import legacy  # noqa: E402
from legacy import Store, person  # noqa: E402
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
            run(c, url, admin)
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


def run(c, url, admin):
    vendored()
    legacy.apply(c)
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
    ids = dict(bike=bike, drive=drive, fit=fit, chain=chain, other=other)

    why = kernelfx.available()
    if why:
        check("the kernel backend can be tested here", False, why)
        return
    k = kernelfx.Kernel(admin)
    try:
        out = k.export(url)
        check("the store is exported into a kernel", out["new"] > 0 and out["not_applied"] == 0, out)
        scenario("kernel", url, k.url, ids)
        kernel_only(k, url, ids)
    finally:
        k.close()


def scenario(backend, url, kernel, ids):
    bike, drive, fit, chain, other = (ids[x] for x in ("bike", "drive", "fit", "chain", "other"))
    srv = server.serve("127.0.0.1", 0, kernel)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    try:
        st, h, body = get(base, "/")
        check(f"[{backend}] the page is served", st == 200 and b"app.js" in body, st)
        for path in ("/", "/static/app.js", "/api/wholes", "/nope"):
            st, h, _ = get(base, path)
            csp = h.get("Content-Security-Policy", "")
            check(f"[{backend}] {path} carries the CSP", "script-src 'self'" in csp and "style-src 'self'" in csp and "unsafe" not in csp, csp)
        st, h, body = get(base, "/static/vendor/cytoscape/cytoscape.min.js")
        check(f"[{backend}] vendored scripts are served as JavaScript", st == 200 and "javascript" in h.get("Content-Type", ""), (st, h.get("Content-Type")))
        wholes = json.loads(get(base, "/api/wholes")[2])
        check(f"[{backend}] wholes: what has parts", [w["id"] for w in wholes] == [bike] and wholes[0]["parts"] == 1, wholes)
        m = json.loads(get(base, f"/api/map/{bike}")[2])
        kinds = {n["id"]: n["kind"] for n in m["nodes"]}
        check(f"[{backend}] a map's nodes by kind", kinds == {bike: "whole", chain: "part", drive: "role", fit: "interface", other: "candidate"}, kinds)
        edges = {(e["source"], e["target"], e["kind"]) for e in m["edges"]}
        check(f"[{backend}] a map's edges by kind", {(bike, chain, "has-part"), (chain, drive, "plays"), (drive, fit, "requires"),
                                                      (chain, fit, "provides"), (other, drive, "could-fill")} <= edges, edges)
        check(f"[{backend}] a map's edges carry no flag and a statement for the stated ones",
              all(e["flagged"] is False for e in m["edges"]) and all(e["statement"] for e in m["edges"] if e["kind"] in ("has-part", "requires", "provides")), m["edges"])
        deep = json.loads(get(base, f"/api/map/{bike}?depth=1")[2])
        check(f"[{backend}] a depth limits the map", {n["id"] for n in deep["nodes"]} >= {bike, chain}, deep)
        e = json.loads(get(base, f"/api/entity/{bike}")[2])
        check(f"[{backend}] an entity's page and whether it has a map", e["has_map"] and e["markdown"].startswith(f"# bicycle ({bike})")
              and e["label"] == "bicycle" and e["description"] == "a whole", e)
        e2 = json.loads(get(base, f"/api/entity/{chain}")[2])
        check(f"[{backend}] a part's page shows its role as a qualifier of the whole's statement, and it has no map",
              not e2["has_map"] and "provides interface" in e2["markdown"].lower(), e2)
        hits = json.loads(get(base, "/api/search?q=chain")[2])
        check(f"[{backend}] search finds", chain in [x["id"] for x in hits] and all({"id", "label", "description"} <= set(x) for x in hits), hits)
        check(f"[{backend}] an empty search finds nothing", json.loads(get(base, "/api/search?q=")[2]) == [])
        check(f"[{backend}] an unknown entity is 404", get(base, "/api/entity/Q999999")[0] == 404)
        check(f"[{backend}] an id that is not one is 404", get(base, "/api/map/x;drop")[0] == 404)
        for path in ("/static/../server.py", "/static/%2e%2e/server.py", "/static/vendor/../../server.py"):
            check(f"[{backend}] nothing outside ui/static: {path}", get(base, path)[0] == 404)
    finally:
        srv.shutdown()


def kernel_only(k, url, ids):
    """The kernel's own rules reach the UI: its session is the read model's role, read-only, and sees only the scopes
    that role is cleared for."""
    st = server.Store(k.url, role=server.KERNEL_ROLE)
    check("[kernel] the UI's session is the read model's role", st.query("select current_user")[0][0] == server.KERNEL_ROLE)
    try:
        st.query("create table x (a int)")
        check("[kernel] its session is read-only", False)
    except psycopg.Error as err:
        check("[kernel] its session is read-only", "read-only" in str(err), err)
    os.environ["KERNEL_URL"] = k.url
    try:
        check("[kernel] the kernel's address is KERNEL_URL when it is set", server.kernel_url() == k.url)
    finally:
        del os.environ["KERNEL_URL"]
    # A claim in a scope the reader is not cleared for is in no answer
    scope = "urn:kk:scope:ui-private"
    with psycopg.connect(k.admin, autocommit=True) as a:
        a.execute("insert into kernel.scope(iri, label) values (%s, 'ui test: private')", (scope,))
        for role, w in (("kkm_encoder_substrate", True), ("kkm_validator", False)):
            a.execute("insert into kernel.scope_grant(scope, db_role, can_read, can_write) values (%s, %s, true, %s)", (scope, role, w))
    with psycopg.connect(url, autocommit=True) as sc:
        s = Store(sc, actor="test-private")
        with s.edit("something private"):
            vault = s.item("Zebrafish vault", description="a secret whole")
            part = s.item("Zebrafish part")
            s.say(vault, s.id("has-part"), part, by=person("pete"))
    cmd = [sys.executable, "-m", "encoder_substrate", "--store", url, "--scope", scope]
    subprocess.run(cmd, check=True, env=k.env, capture_output=True)
    k.wait_applied()
    srv = server.serve("127.0.0.1", 0, k.url)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    try:
        with psycopg.connect(k.admin, autocommit=True) as a:
            n = a.execute("select count(*) from api.claims where scope = %s", (scope,)).fetchone()[0]
        check("[kernel] the private items are claims in a private scope", n > 0, n)
        hidden = [json.loads(get(base, "/api/search?q=zebrafish")[2]), [w["id"] for w in json.loads(get(base, "/api/wholes")[2])],
                  get(base, f"/api/entity/{vault}")[0], json.loads(get(base, f"/api/map/{vault}")[2]).get("nodes")]
        check("[kernel] the UI finds nothing of them: not in search, wholes, a page or a map",
              hidden[0] == [] and vault not in hidden[1] and hidden[2] == 404 and hidden[3] in ([], None), hidden)
        with psycopg.connect(k.admin, autocommit=True) as a:
            a.execute("insert into kernel.scope_grant(scope, db_role, can_read, can_write) values (%s, %s, true, false)", (scope, server.KERNEL_ROLE))
        found = json.loads(get(base, "/api/search?q=zebrafish")[2])
        check("[kernel] once the role is cleared for the scope, the UI finds them", vault in [x["id"] for x in found]
              and vault in [w["id"] for w in json.loads(get(base, "/api/wholes")[2])], found)
    finally:
        srv.shutdown()


if __name__ == "__main__":
    main()
