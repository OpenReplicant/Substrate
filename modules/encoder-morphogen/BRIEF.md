# encoder-morphogen: verdicts as claims

**Built in kernel** (kernel D-99, PR OpenReplicant/kernel#108): `repos/kernel/modules/encoder-morphogen`, because
kernel's modules come only from its own repository (kernel D-43). This brief is what substrate asked for; the
module's manifest and its decision row are what was built. Substrate runs it with `scripts/verdicts.sh`, and the
PostToolUse hook in `.claude/settings.json` runs that after each Morphogen tool call.

The open question below is answered: `measured` is observed, `simulated` inferred (kernel D-99).

---

# encoder-morphogen: verdicts as claims

**For:** kernel should know what was judged, on what evidence, and at what cost, so recall can cite it,
the MAPE-K loop can weigh it, and people can review it beside everything else (S-08). Morphogen's
evidence log stays the integrity record; this module copies, it never replaces.

**Pattern:** kernel's `modules/evaluator` (D-71), which already records eval scores as DQV claims. Same
kind (`control`), slot `evaluator`, runtime `command`.

## Input

Morphogen's evidence log (SQLite in the target project's git directory; `morphogen evidence --verify`
checks its hash chain first). One verdict at a time, oldest first; a cursor of the last entry recorded
lives in kernel as a claim, so re-running changes nothing.

## Output, per verdict

- the verdict's artifact: the log entry's JSON, stored in the artifact store, referenced by its hash;
- `urn:kk:verdict:<id> dqv:value <gain>` qualified by `dqv:isMeasurementOf urn:kk:metric:<cell>:<metric>`
  and `dqv:computedOn` the candidate commit;
- the outcome (pass or refuse, with the reason), the p-value, the system guard's comparison, each setting's
  base and candidate value, as qualifiers or further claims in standard terms;
- PROV: the verdict `prov:wasGeneratedBy` a judge run, `prov:used` the base and candidate commits;
- the cell, named by its Backstage ref when it has one, so it links to `encoder-backstage`'s claims.

## Tests first

- a fixture evidence log with one pass and one refusal gives exactly the expected claims;
- the same log again submits nothing;
- a log whose hash chain is broken is refused, and the refusal is itself recorded;
- claims are attributed to the module's own agent, never to Morphogen or the caller.

## Open

Whether a verdict's `trust: measured` maps to kernel evidence type `observed` or `deterministic`
(kernel spec, evidence types); decide with kernel's owner.
