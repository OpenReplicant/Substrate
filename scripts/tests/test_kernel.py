"""The Knowledge Kernel as Substrate's store (S-153, S-154; the old `store` package is retired, S-156), in a throwaway
kernel it drops after (ADMIN_URL from scripts/test.sh). A small fixture (scripts/tests/seed.py) is submitted into the
kernel directly. It should:
- seed: the items and statements apply, and seeding again submits nothing
- answer the agent's tools over the kernel's MCP server in the substrate profile (search, read, expand, locate, path,
  alternatives, violations, create_item, say, deprecate) with claim handles and belief
- write as the calling agent's claims, and deprecate only its own

It needs the kernel's `kk` command and modules (scripts/tests/kernelfx.py), pgvector and pg_trgm. Not pgGraph, pgmq
or pg_cron.

    scripts/test.sh scripts/tests/test_kernel.py
"""
import asyncio
import json
import os
import re
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kernelfx  # noqa: E402
from seed import Seed, person  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print(("ok  " if ok else "FAIL"), name, "" if ok else detail)


def main():
    try:
        asyncio.run(kernel_part(os.environ["ADMIN_URL"]))
    except Exception as e:                                  # a missing kernel is a failure, named
        checks.append(False)
        print("FAIL the kernel part:", type(e).__name__, e)
    print(f"{sum(checks)}/{len(checks)} checks passed")
    sys.exit(0 if all(checks) else 1)


def kernel_fixture():
    """A store with what the agent's tools are asked about: a hammer with an alias, a preferred and a deprecated
    statement; a bicycle taken apart into a part with a role, an interface, and a candidate."""
    s = Seed()
    me = person("tester")
    ids = {}
    tool = s.item("tool", key="tool")
    hammer = s.item("hammer", key="hammer", description="a tool for nails", aliases=["mallet"])
    s.say(hammer, "instance-of", tool, by=me)
    old = s.say(hammer, "described-at-url", "https://old.example/hammer", by=me)
    s.say(hammer, "described-at-url", "https://example.org/hammer", by=me, rank="preferred")
    s.say(hammer, "described-at-url", "https://example.org/forged-hammer", by=me, rank="preferred")
    s.rank(old, "deprecated", "moved")
    bike = s.item("bicycle")
    drive = s.item("drivetrain role")
    s.say(drive, "instance-of", s.id("role"), by=me)
    fit = s.item("1/2 x 3/32 inch chain fitting")
    s.say(fit, "instance-of", s.id("interface"), by=me)
    s.say(drive, "requires-interface", fit, by=me)
    chain, belt, other = s.item("derailleur chain"), s.item("belt drive"), s.item("single-speed chain")
    for x in (chain, other):
        s.say(x, "provides-interface", fit, by=me)
    s.say(bike, "has-part", chain, by=me, qualifiers=[("object-has-role", drive)])
    ids.update(tool=tool, hammer=hammer, bike=bike, drive=drive, fit=fit, chain=chain, belt=belt, other=other)
    return s, ids


async def kernel_part(admin):
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
    why = kernelfx.available()
    if why:
        raise RuntimeError(why)
    k = None
    try:
        fixture, ids = kernel_fixture()
        k = kernelfx.Kernel(admin)
        out = k.seed(fixture)
        check("kernel: the fixture's items and statements are submitted and applied", out["new"] > 0 and out["not_applied"] == 0, out)
        check("kernel: seeding again submits nothing", k.seed(fixture)["new"] == 0)
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


if __name__ == "__main__":
    main()
