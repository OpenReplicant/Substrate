"""The store (S-135), in a throwaway database it drops after (ADMIN_URL from scripts/test.sh). It should:
- apply its schema once, and again without change
- refuse a value that does not fit its property's datatype, a statement with no reference, an edit of a
  statement's value, and a write by no one; accept every datatype in its Wikidata form
- give the usable value as Wikidata does (preferred if any, else normal), and hide deprecated ones on the page
- report constraint violations (single value, format, one of, value type) without blocking the write
- keep one revision per entity per transaction, naming who edited
- pin spans: an unchanged re-read changes nothing; a changed or vanished span flags what cites it and what was
  derived from that, and nothing else, with no model call; the old text stays readable; re-citing clears it
- find, read, expand, locate, path and alternatives, directly and over MCP (stdio), reconnecting after a restart, and
  write over MCP as claims:
  the client as interpreter, at normal rank, deprecating only its own
- take a whole apart into parts with roles, and find what else provides every interface a role requires; give
  the map as nodes and edges
- report cited file lines that are no longer at their locator (moved, changed or gone)
- import v1's people's statements and decisions as readable pages (when v1's database is in the same Postgres)

    scripts/test.sh scripts/tests/test_store.py
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import store  # noqa: E402
from store import NONE, SOME, Store, interpreter, paragraphs, parser, person, rule  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print(("ok  " if ok else "FAIL"), name, "" if ok else detail)


def refused(fn, needle=""):
    try:
        fn()
    except psycopg.Error as e:
        return needle in str(e)
    return False


def main():
    admin = os.environ["ADMIN_URL"]
    name = f"store_test_{os.getpid()}"
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


def run(c, url, admin):
    check("the schema applies", store.migrate(c) == ["001_store.sql", "002_graph.sql", "003_components.sql", "004_map.sql",
                                                    "005_environment.sql", "006_logins.sql"])
    check("the graph builds", store.project(c)["nodes"] > 0)
    check("and applying it again changes nothing", store.migrate(c) == [])

    nobody = psycopg.connect(url, autocommit=True)
    check("a write by no one is refused", refused(lambda: nobody.execute("select store.new_entity('item', 'x')"), "store.actor"))
    nobody.close()

    s = Store(c, actor="test")
    me = person("tester")
    with s.edit("the test's vocabulary"):
        thing = s.item("thing", key="thing")
        tool = s.item("tool", key="tool")
        s.say(tool, s.id("subclass-of"), thing, by=me)
        km = s.item("kilometre", key="km")
        pt = {dt: s.property(f"a {dt}", dt, key=f"t-{dt}") for dt in
              ("item", "property", "string", "quantity", "time", "coordinate", "url", "external-id")}
        hammer = s.item("hammer", key="hammer", description="a tool for nails", aliases=["mallet"])
        s.say(hammer, s.id("instance-of"), tool, by=me)

    # Typed values
    good = [("item", thing), ("property", pt["url"]), ("string", "steel"), ("quantity", {"amount": 3, "unit": km, "lower": 2, "upper": 4}),
            ("quantity", 1.5), ("time", "2026-11-17"), ("time", "1999"), ("coordinate", (51.5, -0.12)),
            ("url", "https://example.org/x"), ("external-id", "H-1"), ("string", SOME), ("string", NONE)]
    ok = []
    for dt, v in good:
        try:
            s.say(hammer, pt[dt], v, by=me)
            ok.append(True)
        except psycopg.Error as e:
            ok.append(f"{dt} {v!r}: {e}")
    check("every datatype takes its Wikidata form", all(x is True for x in ok), [x for x in ok if x is not True])
    bad = [("item", "steel"), ("item", pt["url"]), ("string", 3), ("string", ""), ("quantity", {"amount": "3"}),
           ("quantity", {"amount": 3, "lower": 4}), ("quantity", {"amount": 3, "unit": "Q99999"}),
           ("time", {"time": "2026-11-17", "precision": 11}), ("time", {"time": "+2026-11-17T00:00:00Z", "precision": 15}),
           ("coordinate", (91, 0)), ("url", "not a url"), ("external-id", {"x": 1})]
    wrong = [f"{dt} {v!r}" for dt, v in bad if not refused(lambda: s.say(hammer, pt[dt], v, by=me), "store:")]
    check("a value that does not fit its datatype is refused", not wrong, wrong)

    def bare():
        with c.transaction():
            c.execute("insert into store.statement (subject, property, value) values (%s, %s, '\"x\"')", (hammer, pt["string"]))
    check("a statement with no reference is refused at commit", refused(bare, "has no reference"))
    st = s.say(hammer, pt["string"], "iron", by=me)
    check("a statement's value is fixed", refused(lambda: c.execute("update store.statement set value = '\"wood\"' where id = %s", (st,)), "fixed"))
    check("statements are not deleted", refused(lambda: c.execute("delete from store.statement where id = %s", (st,)), "deprecated"))

    # Ranks and the usable value
    usable = lambda: sorted(r[0] for r in c.execute(  # noqa: E731
        "select value #>> '{}' from store.usable where subject = %s and property = %s and snak = 'value'", (hammer, pt["string"])))
    check("two normal statements are both usable", usable() == ["iron", "steel"], usable())
    s.rank(st, "preferred")
    check("a preferred one is the only usable one", usable() == ["iron"], usable())
    s.rank(st, "deprecated", reason="it was steel")
    check("deprecated, the normal ones are usable again", usable() == ["steel"], usable())
    page = s.render(hammer)
    check("the page shows usable values and hides the deprecated", "steel" in page and "iron" not in page and "lower rank are not shown" in page, page)
    full = s.render(hammer, all_ranks=True)
    check("all ranks show it, with the reason", "iron (deprecated)" in full and "it was steel" in full, full)
    check("the page formats values", all(x in page for x in ("3 [2 to 4] kilometre", "2026-11-17", "1999", "51.5, -0.12",
                                                            "<https://example.org/x>", "`H-1`", "unknown value", "no value")), page)

    # Constraints: reported, never blocking
    with s.edit("constraints"):
        s.constrain(pt["external-id"], "single-value", by=me)
        s.constrain(pt["external-id"], "format", by=me, regex="H-[0-9]+")
        s.constrain(pt["item"], "value-type", by=me, classes=[tool])
        s.constrain(pt["item"], "one-of", by=me, values=[tool])
    s.say(hammer, pt["external-id"], "h2", by=me)
    kinds = sorted({v["kind"] for v in s.violations() if v["subject"] == hammer})
    check("constraint violations are reported, and the writes stood", kinds == ["format", "one-of", "single-value", "value-type"], s.violations())
    hand = s.item("hand tool", key="hand-tool")             # hammer's item value is thing: make it a hand tool, a kind of tool
    s.say(hand, s.id("subclass-of"), tool, by=me)
    s.say(thing, s.id("instance-of"), hand, by=me)
    check("value type follows instance of, then subclass of", "value-type" not in {v["kind"] for v in s.violations() if v["subject"] == hammer})

    # Revisions
    n0 = c.execute("select count(*) from store.revision where entity_id = %s", (hammer,)).fetchone()[0]
    with s.edit("two statements, one revision"):
        s.say(hammer, pt["string"], "wood", by=me)
        s.say(hammer, pt["string"], "rubber", by=me)
    rows = c.execute("select by, summary from store.revision where entity_id = %s order by id desc", (hammer,)).fetchall()
    check("one revision per entity per transaction, naming who and why", len(rows) == n0 + 1 and rows[0] == ("test", "two statements, one revision"), rows[:2])
    snap = c.execute("select snapshot from store.revision where entity_id = %s order by id desc limit 1", (hammer,)).fetchone()[0]
    check("the revision holds the entity's statements", sum(1 for x in snap["statements"]) >= 15, len(snap["statements"]))

    # Pinned spans and flags
    doc = "The hammer weighs 600 grams.\n\nIts head is steel.\n\nIt was made in 1999."
    spans = s.read_source("file:hammer.md", paragraphs(doc), "text/markdown")
    check("a first read makes a span per paragraph", sorted(ch for _, ch in spans.values()) == ["new"] * 3, spans)
    weight = s.property("mass", "quantity", key="mass")
    grams = s.item("gram", key="g")
    model = interpreter("reader", "1")
    w = s.say(hammer, weight, {"amount": 600, "unit": grams}, by=interpreter("reader", "1", span=spans["p1"][0]))
    h = s.say(hammer, pt["string"], "steel head", by=interpreter("reader", "1", span=spans["p2"][0]))
    y = s.say(hammer, pt["time"], "1999", by=interpreter("reader", "1", span=spans["p3"][0]))
    heavy = s.property("heavier than half a kilo", "string", key="heavy")
    d = s.say(hammer, heavy, "yes", by=rule("mass over 500 g", [w]))
    dd = s.say(hammer, s.id("t-url"), "https://example.org/heavy", by=rule("heavy things get a page", [d]))
    unrelated = s.say(hammer, pt["string"], "painted", by=model)
    again = s.read_source("file:hammer.md", paragraphs(doc))
    check("an unchanged re-read keeps every span and flags nothing", all(ch == "same" for _, ch in again.values()) and s.flags() == [],
          (again, s.flags()))
    changed = s.read_source("file:hammer.md", paragraphs(doc.replace("600", "450").replace("\n\nIt was made in 1999.", "")))
    check("a changed span is superseded and a vanished one gone", changed["p1"][1] == "changed" and changed["p3"][1] == "gone", changed)
    flagged = {f["statement"]: f["reason"] for f in s.flags()}
    check("what cites a changed span is flagged", flagged.get(w) == "its span changed", flagged)
    check("what cites a vanished span is flagged", flagged.get(y) == "its span is gone", flagged)
    check("what was derived from it is flagged, through every step", flagged.get(d, "").startswith("derived") and flagged.get(dd, "").startswith("derived"), flagged)
    check("and nothing else", h not in flagged and unrelated not in flagged and len(flagged) == 4, flagged)
    ev = [e for e in s.locate(w) if "span" in e]
    check("the cited text stays readable, marked changed", ev and ev[0]["span"]["text"] == "The hammer weighs 600 grams." and ev[0]["span"]["changed_since"], ev)
    check("the page marks what is flagged", "flagged: its span changed" in s.render(hammer) and "changed since it was cited" in s.render(hammer))
    s.recite(w, ev[0]["reference"], interpreter("reader", "1", span=changed["p1"][0]))
    flagged = {f["statement"] for f in s.flags()}
    check("re-citing the new span clears it and what was derived from it", w not in flagged and d not in flagged and dd not in flagged and y in flagged, flagged)
    check("spans are pinned", refused(lambda: c.execute("update store.span set text = 'x' where id = %s", (spans["p2"][0],)), "pinned"))

    # Agent tools
    hits = s.search("mallet")
    check("search finds by alias", hits and hits[0]["id"] == hammer, hits)
    check("search finds by a page's words", any(x["id"] == hammer for x in s.search("rubber")), s.search("rubber"))
    check("search takes an id or a key", s.search(hammer)[0]["id"] == hammer and s.search("hammer")[0]["id"] == hammer)
    ex = s.expand(tool)
    check("expand goes out and in", {e["direction"] for e in ex} == {"out", "in"} and any(e["entity"] == hammer for e in ex), ex)
    # The graph follows usable entity-valued statements, in their direction, and keeps up with ranks
    path = s.path(hammer, thing)
    check("a path follows statements", [p["entity"] for p in path] == [hammer, thing] and path[1]["via"] == pt["item"], path)
    via = s.path(hammer, hand)
    check("through other entities", [p["entity"] for p in via] == [hammer, thing, hand], via)
    check("only in their direction", s.path(thing, hammer) == [], s.path(thing, hammer))
    link = c.execute("select id from store.statement where subject = %s and property = %s", (thing, s.id("instance-of"))).fetchone()[0]
    s.rank(link, "deprecated", reason="test")
    check("a deprecated statement leaves the graph", [p["entity"] for p in s.path(hammer, hand)] != [hammer, thing, hand], s.path(hammer, hand))
    check("locate gives a rule's premises", any(e.get("premises") == [w] for e in s.locate(d)), s.locate(d))

    components(c, s, me)
    mcp(url, hammer, s)
    v1(admin, c, s)


def components(c, s, me):
    """A whole taken apart into parts with roles; what could fill a role; a measurement and a verdict."""
    with s.edit("a bicycle"):
        bike = s.item("bicycle")
        drive = s.item("drivetrain role")
        s.say(drive, s.id("instance-of"), s.id("role"), by=me)
        chain_if = s.item("1/2 x 3/32 inch chain fitting")
        s.say(chain_if, s.id("instance-of"), s.id("interface"), by=me)
        s.say(drive, s.id("requires-interface"), chain_if, by=me)
        chain, belt, other = s.item("derailleur chain"), s.item("belt drive"), s.item("single-speed chain")
        for x in (chain, other):
            s.say(x, s.id("provides-interface"), chain_if, by=me)
        s.say(bike, s.id("has-part"), chain, by=me, qualifiers=[(s.id("object-has-role"), drive)])
        speed = s.item("climbing speed")
        s.say(speed, s.id("instance-of"), s.id("goal"), by=me)
        s.say(bike, s.id("has-goal"), speed, by=me)
        s.say(other, s.id("measurement"), {"amount": 12.5}, by=me, qualifiers=[(s.id("for-goal"), speed), (s.id("point-in-time"), "2026-11-17")])
        s.say(other, s.id("verdict"), s.id("verdict-worse"), by=interpreter("judge", "0"),
              qualifiers=[(s.id("for-role"), drive), (s.id("against"), chain), (s.id("for-goal"), speed)])
    alt = {a["entity"]: a for a in s.alternatives(drive)}
    check("alternatives: what provides every interface the role requires", sorted(alt) == sorted([chain, other]) and belt not in alt, alt)
    check("and which fills it now, in which whole", alt[chain]["fills_now"] and alt[chain]["in_whole"] == bike and not alt[other]["fills_now"], alt)
    check("the whole's page shows the part with its role", "has part" in s.render(bike) and "object has role: drivetrain role" in s.render(bike), s.render(bike))
    check("a path runs from the whole through its part to the interface", [p["entity"] for p in s.path(bike, chain_if)] == [bike, chain, chain_if], s.path(bike, chain_if))
    edges = {(a, b, k) for a, b, k in c.execute("select source, target, kind from store.map(%s)", (bike,))}
    kinds = dict(c.execute("select id, kind from store.map_nodes(%s)", (bike,)).fetchall())
    check("the map: whole, part, role and interface as edges",
          {(bike, chain, "has-part"), (chain, drive, "plays"), (drive, chain_if, "requires"), (chain, chain_if, "provides")} <= edges, edges)
    check("and what else could fill a role, not what already does", (other, drive, "could-fill") in edges and not any(k == "could-fill" and a == chain for a, _, k in edges), edges)
    check("its nodes by kind", kinds == {bike: "whole", chain: "part", drive: "role", chain_if: "interface", other: "candidate"}, kinds)
    s.say(belt, s.id("provides-interface"), drive, by=me)
    check("a role given as an interface is reported", any(v["kind"] == "value-type" and v["subject"] == belt for v in s.violations()))

    # Cited file lines checked against the file: unchanged, moved, changed, gone
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "parts.txt"
        f.write_text("alpha\nthe chain fits 1/2 x 3/32\nomega\n")
        sp = s.read_source("file:parts.txt", [("L2", "the chain fits 1/2 x 3/32"), ("L2-3", "the chain fits 1/2 x 3/32\nomega")], "text/plain")
        s.say(chain, s.id("described-at-url"), "https://example.org/chain", by=interpreter("reader", "1", span=sp["L2"][0]))
        s.say(other, s.id("described-at-url"), "https://example.org/other", by=interpreter("reader", "1", span=sp["L2-3"][0]))
        why = lambda: sorted(x["why"] for x in store.stale_file_spans(c, Path(tmp)))  # noqa: E731
        check("cited lines still in their file are not reported", why() == [], why())
        f.write_text("new first line\nalpha\nthe chain fits 1/2 x 3/32\nomega\n")
        check("cited lines that moved, one or several, are reported with where they went", why() == ["moved to L3", "moved to L3"], why())
        f.write_text("alpha\nthe chain fits 1/8 inch\nomega\n")
        check("a cited line that changed is reported", why() == ["not at that locator", "not at that locator"], why())
        f.unlink()
        check("a cited file that is gone is reported", why() == ["file gone", "file gone"], why())


def mcp(url, hammer, s):
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                                                                           "clientInfo": {"name": "test", "version": "0"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "read", "arguments": {"id": hammer}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "search", "arguments": {"query": "mallet"}}},
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "locate", "arguments": {"target": hammer}}},
            {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "nope", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "create_item", "arguments": {
                "label": "claw hammer", "instance_of": "tool", "evidence": {"source": "file:tools.md", "locator": "L3", "quote": "A claw hammer pulls nails."}}}},
            {"jsonrpc": "2.0", "id": 8, "method": "tools/call", "params": {"name": "say", "arguments": {
                "subject": hammer, "property": "t-string", "value": "forged", "note": "from the maker's page",
                "evidence": {"source": "https://example.org/hammer", "locator": "p2", "quote": "Each head is forged."}}}},
            {"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": "say", "arguments": {
                "subject": hammer, "property": "t-quantity", "value": {"amount": "heavy"}}}},
            {"jsonrpc": "2.0", "id": 10, "method": "tools/call", "params": {"name": "create_item", "arguments": {"label": "hammer"}}}]
    p = subprocess.run([sys.executable, "-m", "store.mcp"], input="".join(json.dumps(m) + "\n" for m in msgs), text=True,
                       capture_output=True, cwd=ROOT, env={**os.environ, "STORE_URL": url}, timeout=60)
    out = {m["id"]: m for m in map(json.loads, p.stdout.splitlines())}
    check("MCP: initialize answers the asked version, with tools", out.get(1, {}).get("result", {}).get("protocolVersion") == "2025-11-25"
          and "tools" in out[1]["result"]["capabilities"], (out.get(1), p.stderr[-500:]))
    check("MCP: a notification gets no answer, and stdout is only messages", sorted(out) == list(range(1, 11)), sorted(out))
    check("MCP: the tools", sorted(t["name"] for t in out[2]["result"]["tools"]) ==
          ["alternatives", "create_item", "deprecate", "expand", "locate", "path", "read", "say", "search", "violations"])
    check("MCP: read gives the page", out[3]["result"]["content"][0]["text"].startswith(f"# hammer ({hammer})"), out[3])
    check("MCP: search finds", out[4]["result"]["content"][0]["text"].startswith(hammer), out[4])
    check("MCP: locate gives the pinned text", "The hammer weighs 450 grams." in out[5]["result"]["content"][0]["text"])
    check("MCP: an unknown tool is a protocol error", out[6].get("error", {}).get("code") == -32602, out[6])
    claw = out[7]["result"]["content"][0]["text"]
    check("MCP: create_item makes an item", not out[7]["result"]["isError"] and claw.startswith("Q"), out[7])
    sid = out[8]["result"]["content"][0]["text"]
    ev = s.locate(sid)
    check("MCP: say writes a claim: the client as interpreter, with its version, at normal rank",
          ev and ev[0]["by"] == "interpreter" and ev[0]["name"] == "test" and ev[0]["version"] == "0" and ev[0]["rank"] == "normal", ev)
    check("MCP: its evidence is a pinned span", ev and ev[0]["span"]["text"] == "Each head is forged.", ev)
    check("MCP: a wrong value comes back as a tool error", out[9]["result"]["isError"] and "quantity" in out[9]["result"]["content"][0]["text"], out[9])
    check("MCP: create_item points to similar items", "similar, already here" in out[10]["result"]["content"][0]["text"], out[10])
    mine = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25", "clientInfo": {"name": "test", "version": "0"}}}
    others = s.c.execute("select s.id from store.statement s join store.cites c on c.statement_id = s.id join store.reference r on r.id = c.reference_id "
                         "where s.subject = %s and r.by_kind = 'person' limit 1", (hammer,)).fetchone()[0]
    dep = [mine, {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "deprecate", "arguments": {"statement": sid, "reason": "test"}}},
           {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "deprecate", "arguments": {"statement": str(others), "reason": "test"}}}]
    p = subprocess.run([sys.executable, "-m", "store.mcp"], input="".join(json.dumps(m) + "\n" for m in dep), text=True,
                       capture_output=True, cwd=ROOT, env={**os.environ, "STORE_URL": url}, timeout=60)
    res = {m["id"]: m for m in map(json.loads, p.stdout.splitlines())}
    check("MCP: a client deprecates its own statement", not res[2]["result"]["isError"] and s.locate(sid)[0]["rank"] == "deprecated", res.get(2))
    check("MCP: but not a person's", res[3]["result"]["isError"] and "person reviews" in res[3]["result"]["content"][0]["text"], res.get(3))

    # A restarted Postgres drops the server's connection: the next call connects again rather than failing
    from store.mcp import Server
    os.environ["STORE_URL"] = url
    try:
        srv = Server()
        call = lambda: srv.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "search", "arguments": {"query": "hammer"}}})  # noqa: E731
        call()
        s.c.execute("select pg_terminate_backend(%s)", (srv.s.c.info.backend_pid,))
        r = call()
        check("MCP: after its connection is cut, the next call reconnects", not r["result"]["isError"] and hammer in r["result"]["content"][0]["text"], r)
    finally:
        del os.environ["STORE_URL"]


def v1(admin, c, s):
    from store import import_v1
    v1url = admin.rsplit("/", 1)[0] + "/workbench"
    try:
        old = psycopg.connect(v1url, autocommit=True)
    except psycopg.OperationalError:
        print("skip v1's import: no workbench database here")
        return
    with old:
        old.execute("set default_transaction_read_only = on")
        imp = Store(c, actor="store:import-v1")
        counts = import_v1.run(old, imp)
        check("v1's people's and Claude Code's statements are imported", counts["statements"] >= 200, counts)
        check("and its open decisions", counts["decisions"] >= 44, counts)
        again = import_v1.run(old, imp)
        check("importing again adds nothing", again["statements"] == 0 and again["decisions"] == 0, again)
    wb = imp.search("workbench")
    page = imp.render(wb[0]["id"]) if wb else ""
    check("an imported component reads as a page, with its references", "## References" in page and "person w1-editor" in page, page[:1500])
    dec = c.execute("select id from store.entity where key like 'v1:wb.decision:%' and kind = 'item' limit 1").fetchone()
    check("an imported decision reads as a page", dec and "status (v1)" in imp.render(dec[0]), dec)
    check("every imported statement has a reference", c.execute(
        "select count(*) from store.statement s where not exists (select 1 from store.cites c where c.statement_id = s.id)").fetchone()[0] == 0)


if __name__ == "__main__":
    main()
