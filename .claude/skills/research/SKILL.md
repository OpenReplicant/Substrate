---
name: research
description: Choose a component, library, service, model or vocabulary for Substrate itself, or for a target it builds, from catalogs instead of from memory - name the role in the map, find candidates with the catalog skill, test the shortlist, and record the pick in the map and DECISIONS.md. Use when a step or the owner needs something picked ("which X should we use", "is there something that does"), or before adding any part, package or image.
---

# Research: a choice, from catalogs, not memory

The catalog skill applied to the repository you are in, with its house rules on top (its CLAUDE.md). What you
remember about a tool is a lead; every fact that decides the choice comes from a registry's answer, the tool's
own docs or a trial you ran.

1. **The role and the need, first.** Find the role in the map (the map skill if it is not there). Write the need
   before looking at candidates: the APIs the role requires, and a `Goal` for whatever is measured. The house
   rules are part of the need (licence, a release at least two weeks old, pinned exactly).
2. **Candidates:** the catalog skill, at least three, from more than one catalog.
3. **Test the shortlist:** a trial script under `trials/<slug>/` runs every candidate on the same cases and
   prints one line per candidate and case, output in `.state/trials/<slug>/`. Pin every image and package; fetch
   with checksums. Test each need, not what is easy to measure.
4. **Record the pick:** the role's `filledBy` in the map, by pull request; rejected candidates keep their files,
   with a note on what would make one the pick; a new row in `DECISIONS.md` (what was pinned, where it was read,
   the candidates and why the others lost).
