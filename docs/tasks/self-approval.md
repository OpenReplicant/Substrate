# Task: the moderation queue refuses a decision by whoever raised it

**Model:** Opus. **Needs:** the owner's yes (it changes who may approve, which is floor). **Before:** any
agent login decides anything. `docs/contracts/workflow.md`, rule 2 and "Open".

## Scope

`api.decide` (`workbench/workbench/sql/003_decisions_api.sql`) sets `decided_by` and checks only the editor
role. S-37 says the old kernel refused self-approval (KK025); Workbench does not. Make it: a decision cannot
be approved or declined by the author who raised it. Withdrawing your own stays allowed.

First confirm the gap with a failing test (raise as one author, decide as the same, expect a refusal), so the
fix is shown to be needed.

Decide and record: what "the same author" means when an extractor raises on a person's behalf (the decision's
`raised_by` is the extractor's id, the session's author is `claude-code`). Recommend: compare `wb.author()`
with the decision's `raised_by` and with the author of the claim that raised it, and refuse on either.

## Files to touch

A new migration in `workbench/workbench/sql/` (next number; never edit an applied one), a test in
`workbench/tests/`, `workbench/BRIEF.md` where it describes decisions, `DECISIONS.md` (one row).

## Leave alone

Anything that names Substrate, Morphogen or a plugin: this is Workbench's rule for any user of it. The
handlers plugin's `review-lane` handler already treats a decision by its raiser as no outcome; do not change
it. The automation levels of S-37.

## Done when

The new test fails before the migration and passes after; `scripts/test.sh` passes; the two decisions open in
the queue today can still be decided by the owner; `scripts/check.sh` passes.
