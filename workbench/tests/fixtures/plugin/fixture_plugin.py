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
    ctx.done("note")
    for slug in inputs.get("flag", "").split(","):
        if slug:
            ctx.decision("gap", f"flag:{slug}", {"text": f"{slug} looks odd"})


def register(wb):
    wb.extractor("notes", notes, "notes from text, one per line as slug: body")
