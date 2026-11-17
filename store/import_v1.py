"""v1's people's statements and open decisions, imported into the store as data (S-137). Read-only on v1.

    bin/in-tools python3 scripts/db.py import-v1

What comes over, from v1's database `workbench` (dumped in .state/backups/ on 2026-11-17):
- every claim a person (w1-editor) or Claude Code made, except v1's own bookkeeping (`_retired`). A person's
  claim gets a person's reference and Claude Code's an interpreter's; current ones are at normal rank, superseded
  and retracted ones deprecated with the reason. An object (annotations) becomes a statement per key; a list of
  component names becomes item-valued statements, one per name.
- every open decision, and every decision a person decided, as an item with its text, kind, status and who
  raised and decided it.
v1 recorded no interview answers (the interview skill was built but never wrote one), so there are none to bring.
Parsers' and extractors' output is not imported: rerun the parser instead (S-135).

Run again, it adds nothing twice: each imported statement's reference notes its v1 claim id.
"""
from __future__ import annotations

import json

from store import Store, interpreter, parser, person

PEOPLE = ("w1-editor",)                # v1's logins that were people (wb_private.person); pete decided in the review lane
INTERPRETERS = ("claude-code",)
RELATIONS = ("consumes_apis", "provides_apis", "depends_on", "subcomponent_of")
LABELS = {"consumes_apis": "consumes API", "provides_apis": "provides API", "depends_on": "depends on",
          "subcomponent_of": "subcomponent of"}


class Importer:
    def __init__(self, v1, s: Store):
        self.v1, self.s = v1, s
        self.items: dict[str, str] = {}
        self.slugs = {slug: (cid, title, desc) for cid, slug, title, desc in
                      v1.execute("select id::text, slug, title, description from content.component")}
        self.counts = {"statements": 0, "skipped (already imported)": 0, "decisions": 0}

    def known(self, note: str) -> bool:
        return self.s.c.execute("select 1 from store.reference where note = %s", (note,)).fetchone() is not None

    def cls(self, name: str) -> str:
        return self.s.item(f"v1 {name}", key=f"v1:class:{name}", description=f"a {name} in v1's Workbench (v1-final)")

    def prop(self, key: str, label: str, datatype: str) -> str:
        return self.s.property(label, datatype, key=f"v1:{key}", description=f"v1's {key.split(':', 1)[-1]}, as v1 stated it")

    def subject(self, kind: str, sid: str) -> str:
        k = f"v1:{kind}:{sid}"
        if k in self.items:
            return self.items[k]
        row = None
        if kind == "component":
            row = self.v1.execute("select slug, title, description from content.component where id = %s", (sid,)).fetchone()
        elif kind == "question":
            row = self.v1.execute("select slug, title, question from content.question where id = %s", (sid,)).fetchone()
        slug, title, desc = row or (None, f"v1 {kind} {sid[:8]}", None)
        q = self.s.item(title or slug, key=k, description=desc or f"a v1 {kind}")
        if self.s.c.execute("select 1 from store.statement where subject = %s", (q,)).fetchone() is None:
            ref = parser("import-v1", "2026-11-17", note=f"v1 content.{kind} {sid}")
            self.s.say(q, self.s.id("instance-of"), self.cls(kind), by=ref)
            if slug:
                self.s.say(q, self.prop("slug", "v1 slug", "external-id"), slug, by=ref)
        self.items[k] = q
        return q

    def named(self, name: str) -> str:
        """A component a relation names: by slug, by api-<slug>, or an item made for the name."""
        slug = name.removeprefix("component:")
        for cand in (slug, f"api-{slug}"):
            if cand in self.slugs:
                return self.subject("component", self.slugs[cand][0])
        k = f"v1:named:{slug}"
        return self.s.item(slug, key=k, description="named by a v1 component's relation; not on v1's map")

    def statements(self) -> None:
        rows = self.v1.execute("""
            select id::text, subject_type, subject_id::text, field, value, author, status, observed_at
            from wb.claim where author = any(%s) and field <> '_retired' order by observed_at, id""",
                               (list(PEOPLE + INTERPRETERS),)).fetchall()
        for cid, stype, sid, fld, value, author, status, at in rows:
            note = f"v1 claim {cid}, {status}, observed {at:%Y-%m-%d}"
            if self.known(note):
                self.counts["skipped (already imported)"] += 1
                continue
            ref = person(author, note=note) if author in PEOPLE else interpreter(author, "unrecorded in v1", note=note)
            rank = "normal" if status == "current" else "deprecated"
            with self.s.edit(f"import v1 claim {cid}"):
                subj = self.subject(stype, sid)
                for prop, v in self.values(fld, value):
                    st = self.s.say(subj, prop, v, by=ref, rank=rank)
                    if rank == "deprecated":
                        self.s.rank(st, "deprecated", f"{status} in v1")
                    self.counts["statements"] += 1

    def values(self, fld, value):
        if fld in RELATIONS:
            p = self.prop(f"field:{fld}", LABELS[fld], "item")
            for name in value if isinstance(value, list) else [value]:
                yield p, self.named(str(name))
        elif isinstance(value, dict):
            for k, v in value.items():
                yield self.prop(f"annotation:{k}", f"{k} (v1 annotation)", "string"), v if isinstance(v, str) else json.dumps(v)
        elif isinstance(value, list):
            p = self.prop(f"field:{fld}", f"{fld} (v1)", "string")
            for v in value:
                yield p, v if isinstance(v, str) else json.dumps(v)
        elif value not in (None, ""):
            yield self.prop(f"field:{fld}", f"{fld} (v1)", "string"), value if isinstance(value, str) else json.dumps(value)

    def decisions(self) -> None:
        rows = self.v1.execute("""
            select id::text, kind, key, subject, status, raised_by, decided_by, decided_at, note, created_at
            from wb.decision where status = 'open' or decided_by = 'pete' order by created_at, id""").fetchall()
        for did, kind, key, subj, status, raised, decided, decided_at, note, created in rows:
            mark = f"v1 decision {did}"
            if self.known(mark):
                self.counts["skipped (already imported)"] += 1
                continue
            text = (subj or {}).get("text") or key
            with self.s.edit(f"import v1 decision {did}"):
                q = self.s.item(text if len(text) <= 100 else text[:97] + "...", key=f"v1:wb.decision:{did}",
                                description=f"a v1 {kind} decision, {status}", prose=text)
                raised_by = parser(raised or "unrecorded", "v1", note=mark)
                say = lambda p, v, by=raised_by: self.s.say(q, p, v, by=by)  # noqa: E731
                say(self.s.id("instance-of"), self.cls("decision"))
                say(self.prop("decision:key", "v1 decision key", "external-id"), key)
                say(self.prop("decision:kind", "decision kind (v1)", "string"), kind)
                say(self.prop("decision:raised-by", "raised by (v1)", "string"), raised or "unrecorded")
                if (subj or {}).get("direction"):
                    say(self.prop("decision:direction", "what would settle it (v1)", "string"), subj["direction"])
                if decided:
                    by = person(decided, note=f"{mark}, decided {decided_at:%Y-%m-%d}")
                    say(self.prop("decision:status", "status (v1)", "string"), status, by)
                    say(self.prop("decision:decided-by", "decided by (v1)", "string"), decided, by)
                    if note:
                        say(self.prop("decision:note", "decision note (v1)", "string"), note, by)
                else:
                    say(self.prop("decision:status", "status (v1)", "string"), status)
            self.counts["decisions"] += 1


def run(v1, s: Store) -> dict[str, int]:
    imp = Importer(v1, s)
    imp.statements()
    imp.decisions()
    return imp.counts
