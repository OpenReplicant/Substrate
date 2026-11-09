"""The test plugin's server side: an extractor that reads notes from its inputs, as a file would give them."""


def notes(ctx, inputs):
    if inputs.get("fail"):
        ctx.upsert("note", "doomed", {"body": "never kept"})
        raise RuntimeError("asked to fail")
    text = inputs["text"]
    src = ctx.source("memory:notes.txt", text.encode(), "text/plain")
    for n, line in enumerate(text.splitlines(), 1):
        slug, body = line.split(":", 1)
        ctx.upsert("note", slug, {"body": body.strip()}, source=src,
                   evidence={"body": {"quote": line, "span": {"start_line": n, "end_line": n}}})
    ids = {}
    for slug in [line.split(":", 1)[0] for line in text.splitlines()]:
        ids[slug] = ctx.conn.execute("select id from api.note where slug = %s", (slug,)).fetchone()[0]
    for pair in (inputs.get("link") or "").split(","):
        if pair:
            a, b = pair.split(">")
            ctx.relate("note", ids[a], "linksTo", "note", ids[b], source=src)
    ctx.done("note")
    for slug in inputs.get("flag", "").split(","):
        if slug:
            ctx.decision("gap", f"flag:{slug}", {"text": f"{slug} looks odd"})


def links(ctx, inputs):
    """Another author relating the same items: a>b pairs, as `mentions`."""
    for pair in inputs["link"].split(","):
        a, b = (ctx.conn.execute("select id from api.note where slug = %s", (s,)).fetchone()[0] for s in pair.split(">"))
        premises = inputs.get("premises")
        ctx.relate("note", a, "mentions", "note", b, quote=inputs.get("quote"),
                   span={"premises": premises} if premises else None)


def register(wb):
    wb.extractor("notes", notes, "notes from text, one per line as slug: body")
    wb.extractor("links", links, "relations between notes, a>b, from another author")
