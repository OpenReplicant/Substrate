---
name: catalog
description: Find alternatives for a role a part plays - search the catalogs (package registries, vendors, parts lists, directories) for candidates that provide the interfaces the role requires, write them into the store with evidence, and set up how they will be measured against the whole's goals. Use when the owner asks what else could do a part's job, whether something better exists, or what to replace a part with; after the map skill has named the role. For Substrate's own components, the research skill wraps this one.
---

# Catalog: what else could fill a role

Works on a role the map skill named (S-139), through the store's MCP tools (`mcp__store__*`). A candidate is an
item that *provides interface* what the role *requires interface*; `alternatives` lists every one that does,
and which fills the role now.

## 1. Read the role

`read` the role and `alternatives` for it. If it requires no interface, that comes first (the map skill, step
3): without one, everything and nothing is an alternative. Read the whole's goals (*has goal*): they say which
candidates are worth measuring.

## 2. Search more than one catalog

A catalog is an item made with `instance_of: catalog` (search for it first): PyPI, npm, crates.io, a container
registry, GitHub, deps.dev, a vendor's range, a standards body's list, a directory of services or people. Search
by need and topic, not by the name you expect; what you remember is a lead, not evidence. For software:
`gh api -X GET search/repositories -f q="topic:TOPIC" -f sort=stars`, deps.dev for a package's versions and
licence, `podman search --list-tags REGISTRY/NAME` for images.

## 3. Write each candidate with what its source says

For each: `create_item`; `say` *catalog id* (`catalog-id`) qualified by *catalog* (`in-catalog`); *described at
URL* (`described-at-url`); and *provides interface* only where a source says so, with that source's words as
`evidence`. A candidate that might provide an interface but no source says so: leave the statement out and note
what would settle it. Rule out early on hard limits (the house rules: licence, a release at least two weeks
old) and say which, with the source quoted.

## 4. Measure, then judge

`alternatives` again: those that fit. Measuring is a trial on the same cases for each candidate and for what
fills the role now, against real data where there is some: a script that prints one line per candidate and
case, its output kept as the source. Each result is a *measurement* (`measurement`) on the candidate,
qualified by *goal* (`for-goal`) and *point in time* (`point-in-time`), with the output as evidence.

Whether a candidate is better is a judge's verdict, not yours: *verdict* (`verdict`: `verdict-better`,
`verdict-worse`, `verdict-same`) qualified by *for role*, *against* and *goal*, cited to the judge. Until a judge
is in the build (Morphogen is out while the owner refactors it), tell the owner the measurements and let them
decide; say what you would pick and why.

## 5. Report

The candidates that fit, the ones ruled out and why, the measurements, and what you recommend. A change to the
whole (a part replaced) is the owner's: once they decide, `say` the new *has part* with its role, and
`deprecate` your own old statement with the reason (a person's is theirs to deprecate).
