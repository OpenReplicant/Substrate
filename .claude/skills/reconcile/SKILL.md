---
name: reconcile
description: Compare the three maps of a thing (blueprint, described, observed) and the record of what happened, and write down the gaps - what is missing, broken, believed wrongly, or could be better - as work for the build skill or changes to the blueprint. Use after a build, when a check or verdict fails, when the owner asks what is wrong or what is left, or on a schedule.
---

# Reconcile: the gaps between what should be, what is believed, and what is

1. **Run the check.** `python3 check.py`: stale evidence is the first kind of gap (a source changed under a
   claim).
2. **Compare by name across namespaces** (`map/blueprint/`, `map/described/`, `map/observed/`):
   - in the blueprint, not observed: not built yet, or lost
   - observed, not in the blueprint: built without a design, or the design is missing it
   - described differently from observed: someone's picture is wrong (say whose, from the evidence)
   - a role whose filler lacks an API the role requires; a goal with no measurement, or one off its target
3. **Read the record:** recent pull requests and their verdicts (`gh pr list --state all`, the checks on each),
   refused changes and why, failing checks. A refusal that repeats is a gap in the blueprint or the tests.
4. **Write the gaps** to `GAPS.md` at the repository's root: one line each, with the evidence (the entity, the
   file and line, the pull request), what kind of gap, and what would close it (build it, change the blueprint, ask
   the owner). Replace the file each time; git keeps what it said before.
5. **Hand over:** gaps that are clear work go to the build skill; gaps that are design questions go to the owner,
   with a recommendation.
