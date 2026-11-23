"""Fixtures for the tests that read Substrate's store from the Knowledge Kernel: items and statements built in memory
and submitted straight into a throwaway kernel (kernelfx.Kernel.seed), with no `store` schema (dropped, S-191).

The rows are the plain dicts the kernel's encoder-substrate takes (its encode.py: entities and statements with
qualifiers and references), so the claims have the shapes the kernel's read model and its `substrate` MCP profile
answer from.

    s = Seed()
    me = person("tester")
    hammer = s.item("hammer", description="a tool for nails", aliases=["mallet"])
    old = s.say(hammer, "described-at-url", "https://old.example/hammer", by=me)
    s.rank(old, "deprecated", "moved")
    k.seed(s)                       # kernelfx.Kernel: submitted and applied
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

# The properties the tests use, with the datatype the encoder reads their values by (the old store's keys,
# which encoder-substrate maps to Wikidata's and Substrate's pack terms).
PROPERTIES = {
    "instance-of": "item", "subclass-of": "item", "has-part": "item", "object-has-role": "item",
    "requires-interface": "item", "provides-interface": "item", "described-at-url": "url",
    "reason-for-deprecated-rank": "string", "for-role": "item", "in-catalog": "item", "catalog-id": "external-id",
}
# Items the kernel's packs already define, by the key encoder-substrate knows them by.
PACK_ITEMS = ("role", "interface", "goal", "catalog")


@dataclass(frozen=True)
class Ref:
    kind: str
    name: str
    version: str | None = None


def person(name: str) -> Ref:
    return Ref("person", name)


class Seed:
    def __init__(self, first: int = 1):
        """`first`: the first item's number, so a second seed into the same kernel makes ids of its own."""
        self.entities: dict[str, dict] = {}
        self.statements: list[dict] = []
        self._by_key: dict[str, str] = {}
        self._n = first - 1
        for i, (key, dt) in enumerate(PROPERTIES.items(), 1):
            self._add(f"P{i}", "property", key, key.replace("-", " "), datatype=dt)
        for key in PACK_ITEMS:
            self.item(key, key=key)

    def _add(self, eid, kind, key, label, description=None, aliases=(), datatype=None):
        self.entities[eid] = {"id": eid, "kind": kind, "datatype": datatype, "key": key, "label": label,
                              "description": description, "aliases": list(aliases), "prose": None}
        if key:
            self._by_key[key] = eid
        return eid

    def id(self, key: str) -> str:
        return self._by_key[key]

    def item(self, label, key=None, description=None, aliases=()) -> str:
        """A new item; its id is a Qid, as the store's were."""
        self._n += 1
        return self._add(f"Q{self._n}", "item", key, label, description, aliases)

    def _snak(self, prop: str, value) -> dict:
        if self.entities[prop]["datatype"] == "item":
            return {"property": prop, "snak": "value", "value": None, "value_entity": value}
        return {"property": prop, "snak": "value", "value": value, "value_entity": None}

    def say(self, subject, prop, value, *, by: Ref, qualifiers=(), rank="normal") -> str:
        """A statement; `prop` and qualifiers' properties by key. Returns the statement's id."""
        p = self.id(prop)
        st = {"id": str(uuid.uuid4()), "subject": subject, **self._snak(p, value), "rank": rank,
              "qualifiers": [{"ord": i, **self._snak(self.id(qp), qv)} for i, (qp, qv) in enumerate(qualifiers)],
              "references": [{"id": str(uuid.uuid4()), "by_kind": by.kind, "by_name": by.name,
                              "by_version": by.version, "run": None, "span": None}]}
        self.statements.append(st)
        return st["id"]

    def rank(self, statement: str, rank: str, reason: str | None = None) -> None:
        st = next(s for s in self.statements if s["id"] == statement)
        st["rank"] = rank
        if reason:
            st["qualifiers"].append({"ord": len(st["qualifiers"]), **self._snak(self.id("reason-for-deprecated-rank"), reason)})
