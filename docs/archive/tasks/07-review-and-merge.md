# Task 7: review and merge

**Model:** the largest available, then the owner. **Needs:** whichever tasks make up the milestone.

## Scope

Review `direction/experiment-first` against `main` before it merges. A review, not a rewrite: findings go back
to the task that caused them.

Check, in this order:

1. **The floor is untouched by what it judges.** No commit changes `morphogen.yaml`, a scorer, a driver, a
   cases script or `scripts/gateway.py`'s meter in the same commit as the component those judge. Nothing under
   `repos/` differs from the checked commit without a branch and a pull request there.
2. **Nothing held out leaked.** `bin/gitleaks` passes; no file in the diff contains a case outcome, a path
   under the judged directory's `private/`, or a key.
3. **Each contract still describes the code.** For each page in `docs/contracts/`, the fields and rules it
   states against what the diff built. A difference is fixed in whichever is wrong, and said.
4. **Workbench knows nothing of Substrate.** No name of a plugin, stream, environment or benchmark under
   `workbench/`.
5. **The map matches.** `scripts/map.sh export` produces no diff; `bin/morphogen structure check
   morphogen.yaml` reports no error.
6. **The rename changed words only** (task 4's "done when").
7. **Each task's own check**, re-run: `scripts/test.sh`, `scripts/check.sh`, `scripts/contract.sh all`.

## Files to touch

None, except `DECISIONS.md` for a row if the review overturns something.

## Done when

The findings are listed with file and line, each fixed or accepted by the owner; `scripts/check.sh` passes on
the owner's machine; the owner merges. Approval is the owner's, never the session's that did the work
(`docs/contracts/workflow.md`, rule 2).
