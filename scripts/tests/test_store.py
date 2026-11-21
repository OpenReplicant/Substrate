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

and, on the Knowledge Kernel that is Substrate's store now (S-153, S-154), in a throwaway kernel the same store is
exported into (scripts/tests/kernelfx.py): the export applies, and exporting again submits nothing; the agent's tools
over the kernel's MCP server in the substrate profile (search, read, expand, locate, path, alternatives, create_item,
say, deprecate; no `violations`) answer as the store's do, with claim handles and belief added, and write as the
calling agent's claims; the read model's pages and maps are the store's. The first part needs the stack's Postgres
(pgGraph, pgmq, pg_cron): without it that part is skipped and says so; the kernel part needs only the store's
migrations 001, 003 and 004, pgvector and pg_trgm.

    scripts/test.sh scripts/tests/test_store.py
"""
import asyncio
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kernelfx  # noqa: E402
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
    with psycopg.connect(admin, autocommit=True) as a:
        have = {r[0] for r in a.execute("select name from pg_available_extensions where name in ('graph', 'pgmq', 'pg_cron')")}
    if have == {"graph", "pgmq", "pg_cron"}:
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
    else:
        print(f"skip the store schema's checks: this Postgres lacks {sorted({'graph', 'pgmq', 'pg_cron'} - have)}")
    try:
        asyncio.run(kernel_part(admin))
    except Exception as e:                                  # a missing kernel is a failure, named
        checks.append(False)
        print("FAIL the kernel part:", type(e).__name__, e)
    print(f"{sum(checks)}/{len(checks)} checks passed")
    sys.exit(0 if all(checks) else 1)


def run(c, url, admin):
    check("the schema applies", store.migrate(c) == ["001_store.sql", "002_graph.sql", "003_components.sql", "004_map.sql",
                                                    "005_environment.sql", "006_logins.sql", "007_components.sql"])
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


# ---- the Knowledge Kernel as the store (S-154) -----------------------------------------------------------------------
def kernel_fixture(c):
    """A store with what the agent's tools are asked about: a hammer with an alias, a preferred and a deprecated
    statement; a bicycle taken apart into a part with a role, an interface, and a candidate."""
    for f in ("001_store", "003_components", "004_map"):
        with c.transaction():
            c.execute((store.SQL / f"{f}.sql").read_text())
    s = Store(c, actor="test")
    me = person("tester")
    ids = {}
    with s.edit("the kernel test's things"):
        tool = s.item("tool", key="tool")
        hammer = s.item("hammer", key="hammer", description="a tool for nails", aliases=["mallet"])
        s.say(hammer, s.id("instance-of"), tool, by=me)
        old = s.say(hammer, s.id("described-at-url"), "https://old.example/hammer", by=me)
        s.say(hammer, s.id("described-at-url"), "https://example.org/hammer", by=me, rank="preferred")
        s.say(hammer, s.id("described-at-url"), "https://example.org/forged-hammer", by=me, rank="preferred")
        s.rank(old, "deprecated", "moved")
        bike = s.item("bicycle")
        drive = s.item("drivetrain role")
        s.say(drive, s.id("instance-of"), s.id("role"), by=me)
        fit = s.item("1/2 x 3/32 inch chain fitting")
        s.say(fit, s.id("instance-of"), s.id("interface"), by=me)
        s.say(drive, s.id("requires-interface"), fit, by=me)
        chain, belt, other = s.item("derailleur chain"), s.item("belt drive"), s.item("single-speed chain")
        for x in (chain, other):
            s.say(x, s.id("provides-interface"), fit, by=me)
        s.say(bike, s.id("has-part"), chain, by=me, qualifiers=[(s.id("object-has-role"), drive)])
    ids.update(tool=tool, hammer=hammer, bike=bike, drive=drive, fit=fit, chain=chain, belt=belt, other=other)
    return ids


async def kernel_part(admin):
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
    why = kernelfx.available()
    if why:
        raise RuntimeError(why)
    sname = f"store_kfx_{os.getpid()}"
    with psycopg.connect(admin, autocommit=True) as a:
        a.execute(f"create database {sname}")
    surl = admin.rsplit("/", 1)[0] + "/" + sname
    k = None
    try:
        with psycopg.connect(surl, autocommit=True) as c:
            ids = kernel_fixture(c)
        k = kernelfx.Kernel(admin)
        out = k.export(surl)
        check("kernel: the store's items and statements are exported and applied", out["new"] > 0 and out["not_applied"] == 0, out)
        check("kernel: exporting again submits nothing", k.export(surl)["new"] == 0)
        agent = k.agent("substrate-test")
        env = {x: os.environ[x] for x in ("PATH", "PYTHONPATH", "HOME") if x in os.environ}
        env.update(DATABASE_URL=agent, KK_PROFILE="substrate", KK_SUBSTRATE_WAIT="30")
        params = StdioServerParameters(command=sys.executable, args=["-m", "kernel_mcp"], env=env)
        async with stdio_client(params) as (r, w), ClientSession(r, w) as session:
            await session.initialize()
            await kernel_tools(session, ids, k)
    finally:
        if k:
            k.close()
        with psycopg.connect(admin, autocommit=True) as a:
            a.execute(f'drop database if exists "{sname}" with (force)')


async def kernel_tools(session, ids, k):
    async def call(name, **args):
        res = await session.call_tool(name, args)
        return (res.content[0].text if res.content else ""), res.is_error

    hammer, tool, bike, drive, fit, chain, belt, other = (ids[x] for x in ("hammer", "tool", "bike", "drive", "fit", "chain", "belt", "other"))
    listed = {t.name: t for t in (await session.list_tools()).tools}
    check("kernel MCP: Substrate's ten tools, `violations` among them", set(listed) == {
        "search", "read", "expand", "locate", "path", "alternatives", "violations", "create_item", "say", "deprecate"}, sorted(listed))
    check("kernel MCP: path takes `from` and `to`, as the store's does", set(listed["path"].input_schema["properties"]) == {"from", "to"})
    text, err = await call("violations")
    check("kernel MCP: `violations` answers", not err, text)

    text, err = await call("search", query="mallet")
    check("search finds by an alias, the id first", not err and text.splitlines()[0].split()[0] == hammer, text)
    text, err = await call("search", query="nails")
    check("search finds by the words of the description", hammer in text, text)
    text, err = await call("search", query=hammer)
    check("search takes an id", text.splitlines()[0].split()[0] == hammer, text)

    page, err = await call("read", id=hammer)
    check("read gives the page: label, id, description, alias, the usable statements",
          page.startswith(f"# hammer ({hammer})") and "a tool for nails" in page and "mallet" in page
          and "example.org/forged-hammer" in page and "old.example" not in page, page)
    check("read says how many lower-ranked statements are not shown", "lower rank are not shown" in page, page)
    check("read adds the claims it rests on, with handle and belief", re.search(r"#[0-9a-f]{8}", page) and "belief" in page, page)
    full, _ = await call("read", id=hammer, all_ranks=True)
    check("read with all ranks shows the deprecated one", "old.example" in full and "(deprecated)" in full, full)
    text, err = await call("read", id="Q999999999")
    check("read of an unknown id says there is none", "no entity" in text, text)

    text, err = await call("expand", id=tool)
    check("expand goes out and in", not err and hammer in text, text)
    text, err = await call("path", **{"from": bike, "to": fit})
    check("path runs from the whole through its part to the interface",
          not err and [text.find(x) for x in (bike, chain, fit)] == sorted(text.find(x) for x in (bike, chain, fit)) and chain in text, text)
    text, err = await call("path", **{"from": fit, "to": bike})
    check("path goes only in the statements' direction", "no path" in text.lower() or "none" in text.lower(), text)

    text, err = await call("alternatives", role=drive)
    check("alternatives: what provides every interface the role requires, and which fills it now",
          chain in text and other in text and belt not in text and re.search(rf"{chain}.*(fills|in {bike})", text), text)
    text, err = await call("locate", target=hammer)
    located = json.loads(text)
    check("locate gives each statement's reference, with its claim, handle, belief and who stated it",
          not err and len(located) >= 4 and all({"claim", "handle", "belief", "says", "rank", "by", "name"} <= set(e) for e in located)
          and any(e["says"].startswith("hammer instance of tool") and e["by"] == "person" and e["name"] == "tester" for e in located), text)

    # writing: the calling agent's claims
    ev = {"source": "https://example.org/hammer", "locator": "p2", "quote": "Each head is forged."}
    new, err = await call("create_item", label="claw hammer", instance_of="tool", evidence=ev)
    check("create_item makes an item and answers with its id", not err and re.match(r"Q\d+", new), new)
    qid = new.split()[0]
    page, _ = await call("read", id=qid)
    check("the new item reads as a page, an instance of tool", page.startswith(f"# claw hammer ({qid})") and "instance of" in page.lower(), page)
    text, err = await call("create_item", label="hammer")
    check("create_item points to similar items", "similar, already here" in text, text)
    said, err = await call("say", subject=qid, property="described-at-url", value="https://example.org/claw", evidence=ev, note="from the page")
    check("say writes a claim and answers with its id", not err and re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-", said), said)
    claim = re.search(r"[0-9a-f]{8}-[0-9a-f-]{27}", said).group(0)
    with psycopg.connect(k.admin, autocommit=True) as a:
        row = a.execute("select attributed_to, status, evidence_type from api.claims where id = %s", (claim,)).fetchone()
        refs = a.execute("select source_uri, quote from api.claim_references where claim_id = %s", (claim,)).fetchall()
    check("the claim is the agent's, at normal rank, with its quote as the reference",
          row and row[0] == "urn:kk:agent:substrate-test" and row[1] == "normal" and refs and refs[0][1] == "Each head is forged.", (row, refs))
    text, err = await call("say", subject=qid, property="measurement", value={"amount": "heavy"})
    check("say with a value that does not fit is an error", err, text)
    text, err = await call("deprecate", statement=claim, reason="test")
    check("deprecate: the agent's own claim", not err and "deprecated" in text, text)
    page, _ = await call("read", id=qid)
    check("and the page no longer shows it", "example.org/claw" not in page, page)
    with psycopg.connect(k.admin, autocommit=True) as a:
        theirs = a.execute("select id from api.claims where subject like %s and predicate like '%%P973' and status = 'preferred' limit 1",
                           ("%:" + hammer,)).fetchone()[0]
    text, err = await call("deprecate", statement=theirs, reason="mine now")
    check("deprecate: not someone else's", err and "someone else" in text, text)


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
