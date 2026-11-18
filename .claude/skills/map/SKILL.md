---
name: map
description: Take a thing apart into its parts, the roles each part plays and the interfaces that make parts interchangeable, and write it as Backstage descriptor files with evidence on every claim - any thing (a codebase, a service, a process, a team). Use when the owner asks what something is made of, how its parts fit, what could be swapped or changed, before cataloging alternatives (the catalog skill), and before building toward a spec (the build skill).
---

# Map: what a thing is made of, as designed, described and observed

A map is files: one entity per file under `map/<namespace>/`, each listed as a target of `catalog-info.yaml`,
in the format of `docs/seed.md` ("The map format"). Everything you write is your claim, with its evidence.

## 1. The whole, the question, and which map

Ask what the map is for (what might change, what should get better) if it is not said: it decides how deep to
go. Map to that depth and stop. Then pick the namespace by where the claims come from:
- `blueprint`: a spec, a design, a decision (what should be)
- `described`: what people say or docs claim (what is believed to be)
- `observed`: the thing itself: code, config, a running process, a measurement (what is)

Read what exists first (`ls map/*/`): the same name in another namespace is the same thing; reuse it.

## 2. Parts, roles, interfaces

- A **whole** is a `System`; a **part** a `Component` (built here) or `Resource` (used, not built), with
  `spec.system` or `spec.subcomponentOf` for where it sits.
- A **role** is a `Role` (`openreplicant.com/v1alpha1`): `spec.of` the whole, `spec.filledBy` the part playing
  it now, `spec.requiresApis` what anything filling it must provide. Name it for what it does, so another part
  could do it.
- An **interface** is an `API` whose `spec.definition` says exactly what crosses the boundary: an API and its
  version, a file format, a protocol, a standard part. A part that has it lists it in `spec.providesApis`. An
  interface named loosely makes everything look interchangeable.
- What better means, if the owner says: a `Goal` with `spec.metric` (words a judge could apply) and `spec.target`.

Names follow Backstage's rule: letters and digits, separated by `-`, `_` or `.`, at most 63 characters.
References are `kind:name` inside the same namespace, `kind:namespace/name` across.

## 3. Evidence on every claim

Each claim carries an annotation `openreplicant.com/evidence-FIELD` (the field it backs; `-2` for a second
source): `"PATH#La-b sha256:new"` for lines of a file in this repository, `"URL YYYY-MM-DD"` for a page read
outside it. Read the source itself, not your memory of it; cite the smallest stable span (a heading, a definition,
a config line). What a person told you: write it into a file first (a note quoting them, with the date) and cite
that. What you cannot cite, leave out or ask about. Then `python3 check.py --stamp` fills in the hashes.

## 4. Check

`python3 check.py`: every file listed, every reference resolves, every name and kind is valid, no evidence stale.
A stale citation means the source changed: re-read it, then fix the claim or re-cite it. Tell the owner what is
mapped, what was left out and why, what you are unsure of. Morphogen reads the same files (its Backstage loader)
when it judges.
