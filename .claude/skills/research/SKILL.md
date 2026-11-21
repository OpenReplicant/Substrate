---
name: research
description: Choose a component, library, service, model or vocabulary for Substrate itself from the catalogs instead of from memory - name the role on Substrate's map, find candidates with the catalog skill, test the shortlist against the need, and record the pick in the store and DECISIONS.md. Use when a step or the owner needs something picked ("which X should we use", "find a library for", "is there something that does"), or before adding any part, package or image.
---

# Research: Substrate's own choices, from catalogs, not memory

The catalog skill applied to Substrate (S-139), with the house rules on top. What you remember about a tool is
a lead, not evidence: every fact that decides the choice comes from a registry's answer or a trial you ran.

## 1. The role and the need, first

Find the role on Substrate's map in the store (the kernel's tools, `mcp__kernel__*`: `search` for Substrate, `read` it; the map skill if the part of
it you need is not mapped yet). Write the need before looking at candidates, so candidates are tested against
it rather than the need bent to fit a favourite: the interfaces the role requires (`requires-interface`) and, as
a goal on Substrate (`has-goal`) with a metric and target, whatever is measured. The house rules are always part
of the need: a permissive or LGPL licence in the default stack, a release at least two weeks old, pinned
exactly, one container under Podman for a service, nothing installed on the host.

## 2. Candidates

The catalog skill, steps 2 and 3: at least three, from more than one catalog, each with its catalog id, URL and
the interfaces its sources say it provides. Licence, versions and dates come from the registry's answer
(deps.dev, GitHub's API, the LICENSE file when GitHub says NOASSERTION), quoted as evidence, never written from
memory. Rule out on the house rules early and say which.

## 3. Test the shortlist

A trial script under `scripts/trials/<slug>/` runs every shortlisted candidate on the same cases, against real
data where there is some, and prints one result line per candidate and case (output in `.state/trials/<slug>/`).
Pin every image, jar and package in it; fetch with checksums. Test each need, not what is easy to measure. Each
result goes in as a measurement (the catalog skill, step 4), the output file as its evidence.

When two or more meet the need and the question is which is better, that is a judge's question (Morphogen,
when it is back in the build); until then the measurements and your recommendation go to the owner.

## 4. Record the pick

- In the store: the pick *has part* on Substrate with its role, when a step puts it in; rejected candidates
  keep their statements, and a `note` on what would make one the pick.
- In `DECISIONS.md`, a new row when the pick becomes a default: what was pinned, where it was read, the
  candidates and why the others lost.
