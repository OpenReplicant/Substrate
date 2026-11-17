# Task: rewrite `docs/spec.md` around `docs/direction.md`

**Model:** Opus. **Needs:** tasks 4 (the words) and 6 (so it describes something that runs). Not before:
until then `docs/direction.md` wins where the two disagree, and that is enough.

## Scope

`docs/spec.md` (580 lines, 12 sections, 33 build steps) is the record of what was built under S-41. Rewrite it
as the description of what Substrate is now: three principles, three projects, floor and seed, environments
and value per dollar, the plan. Shorter than today.

- Keep what is built and still true (the stack, the map, the catalogs and how a choice is made, the gateway,
  who decides what), in the new words.
- Move candidates out of the design: the fallback learner, the idle tier, architectures as intended maps,
  volunteered compute and the realtime assistant become entries under one heading, "Hypotheses", each with
  what would test it. `docs/multi-process.md` stays as the fallback learner's longer write-up.
- Point to `docs/contracts/` instead of restating a contract.
- Section 9 and `docs/build.yaml`: replace the build plan with direction's plan table. Ask the owner whether
  `docs/build.yaml` is deleted or kept paused; recommend keeping it paused until step 4 has a verdict.

## Files to touch

`docs/spec.md`, `README.md` and `CLAUDE.md` where they summarise it, `docs/direction.md` (it folds into the
spec, or stays as the short form: say which), `DECISIONS.md` (one row). The old text is in git; do not keep a
copy in the tree.

## Leave alone

`DECISIONS.md`'s existing rows (S-numbers the old spec cites stay valid). `scripts/spec.py` and the
SessionStart hook's logic, unless the owner chooses to delete `docs/build.yaml`. Code.

## Done when

Every section traces to one of the three principles or is under "Hypotheses"; no step number from the old plan
is cited as pending; every relative link resolves; `scripts/check.sh` passes; the owner has read it.
