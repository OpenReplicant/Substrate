---
name: catalog
description: Find alternatives for a role a part plays - search catalogs (package registries, vendors, directories, GitHub) for candidates that provide the interfaces the role requires, write them into the map with evidence, and set up how they will be measured. Use when the owner asks what else could do a part's job, whether something better exists, or what to replace a part with; after the map skill has named the role.
---

# Catalog: what else could fill a role

Works on a `Role` the map skill wrote. A candidate is a `Component` (or `Resource`) in the same namespace with
`spec.lifecycle: candidate`, the annotation `openreplicant.com/candidate-for: role:NAME`, and `spec.providesApis`
only where a source says so. It is an alternative when it provides every API the role requires.

1. **Read the role** and its `requiresApis`. A role that requires nothing comes first (the map skill): without
   interfaces, everything and nothing is an alternative. Read the whole's goals: they say what is worth measuring.
2. **Search more than one catalog**, by need and topic, not by the name you expect; what you remember is a lead,
   not evidence. For software: `gh api -X GET search/repositories -f q="topic:TOPIC" -f sort=stars`, deps.dev for
   versions and licences, `podman search --list-tags` for images, GitHub's API for releases and `license.spdx_id`
   (the LICENSE file itself when it says NOASSERTION).
3. **Write each candidate** with its catalog's URL as evidence (`"URL YYYY-MM-DD"`) for each claim. Rule out on
   hard limits early (the target's licence rules, a release at least two weeks old) and say which, quoting the
   source. A candidate that might provide an interface but no source says so: leave the claim out and say what
   would settle it.
4. **Measure, then judge.** A trial runs every candidate and the current filler on the same cases and prints one
   line per candidate and case; its output is a file, cited by `openreplicant.com/measured-GOAL: "VALUE, PATH,
   DATE"`. Which is better is Morphogen's verdict, not yours: until it is asked, tell the owner the measurements
   and what you would pick and why.
5. **Report** what fits, what was ruled out and why, and the recommendation. Replacing a part is the owner's
   decision: then the role's `filledBy` changes, by pull request (the build skill).
