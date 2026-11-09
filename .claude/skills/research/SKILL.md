---
name: research
description: Choose a component, library, service, model or vocabulary from the catalogs instead of from memory - search the registries in catalog-info.yaml's sources system, record candidates with cited claims, test the shortlist against the need, and record the pick and the rejections in docs/choices for Workbench. Use when a step or the owner needs something picked ("which X should we use", "find a library for", "is there something that does"), or before adding any part, package or image.
---

# Research: choose from catalogs, not memory

A choice is curated, researched and tested (spec section 5). What you remember about a tool is a lead, not
evidence: every fact that decides the choice comes from a registry's answer or a trial you ran.

## 1. Write the need first

Start `docs/choices/<slug>.yaml` with `question`, `asked_by`, `asked_on` (quoted, "YYYY-MM-DD"), the owner's
words in `quote` if they asked, and `need`: three to five things the pick must do, each one testable. The
house rules are always part of it: a permissive or LGPL licence in the default stack, a release at least two
weeks old, pinned exactly, one container under Podman for a service. Write the need before looking at
candidates, so the candidates are tested against it rather than the need bent to fit a favourite.

## 2. Search the source catalogs

`catalog-info.yaml`, system `sources`: each registry says how to search it (`substrate.dev/search`), what it
gives and its limits. Also look in the `options` system: a part already known may fit. Search more than one
registry, by topic and by need rather than by the name you expect. Record each search in `searched` (registry,
query, date). Useful starts:

- GitHub: `gh api -X GET search/repositories -f q="topic:TOPIC" -f sort=stars` (topics find more than words;
  `gh search repos` returns little for multi-word queries)
- deps.dev for a package's versions and licence (Maven, PyPI, npm, Go, Cargo, NuGet)
- `podman search --list-tags REGISTRY/NAME` for images; name the registry
- `awesome-*` lists found this way are leads, never evidence

## 3. Candidates

At least three, as entries under `candidates`: `name` (the slug), `title`, `registry`, `repository`
(owner/name on GitHub) and, for packages, `package: {system, name}` for deps.dev; `fit` (what it does against
the need), `shortlisted`, `outcome` (open, picked or rejected) and `reason`. Do not write licence, versions,
stars or dates by hand: `substrate:choices` reads them from GitHub and deps.dev and quotes the key each came
from. Reject on the house rules early (licence, no release in years) and say which rule, quoting the source
when the registry's answer is not enough (GitHub reports some licences as NOASSERTION; quote the LICENSE file).

## 4. Test the shortlist

A trial script under `scripts/trials/<slug>/` that runs every shortlisted candidate on the same cases, against
real data where there is some, and prints one result line per candidate and case (results in
`.state/trials/<slug>/`). Pin every image, jar and package in the script; fetch jars with their checksums. Test
each need, not what is easy to measure. Record per candidate a `trial` line with the numbers, and in `trial`
at the top the script, cases, date and what was expected.

When two or more candidates meet the need and the question becomes which is better (faster, more accurate,
better answers), that is Morphogen's question: set up a judged comparison and record its verdict in `verdict`.
When the need alone decides it, say so in `verdict` and why.

## 5. Record the pick

`pick` and `reason`: why this one, and what it costs. Each rejected candidate keeps its `reason`, including
what would make it the pick, so a later need starts from evidence. Then:

- `scripts/workbench.sh extract substrate:choices` (also run by `scripts/up.sh`), and check the candidate items
  carry registry quotes (MCP `get_item` type `candidate`)
- the pick goes on the map: an entry in `options` (fits, interface, when, candidates) until a step needs it
  running, then into `core`; `bin/morphogen structure check morphogen.yaml`
- a `DECISIONS.md` row when the pick becomes a default

Recall answers "why this one?" from the choice item and its candidates (MCP `search`, then `get_item`).
