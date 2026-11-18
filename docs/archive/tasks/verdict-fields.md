# Task: the verdict item keeps what the experiments need

**Model:** Sonnet. **Needs:** nothing. **Before:** direction step 3 (labels), step 4 (comparability), step 5
(the cheat log). `docs/contracts/verdict.md`, "What Substrate reads today, and what it will need".

## Scope

The `morphogen` extractor copies part of each verdict record. Add, without changing what is already read:

| Item field | From the record | Type |
| --- | --- | --- |
| `labels` | `labels` | object of strings |
| `scope` | `scope` | as recorded |
| `inputs` | `inputs` (the digest) | string |
| `meter` | `served.gateway.meter` | string |
| `owner`, `lifecycle` | `gate.owner`, `gate.lifecycle` | string |
| in `reasons` | `outcome.parameter_violations`, `outcome.system` | as recorded |

Each new value cites the record the same way the existing ones do (`{"record": seq, "pointer": ...}`). A
record without a field leaves the item's field empty; older verdicts must still load.

## Files to touch

`plugins/substrate/types/verdict.json`, `plugins/substrate/substrate_plugin.py` (the `morphogen` extractor),
`plugins/substrate/tests/test_morphogen.py` (a record with every field, and one with none), then regenerate
the ontology with `plugins/substrate/vocab.py` (never edit `vocabulary.yaml` by hand).

## Leave alone

`repos/morphogen` and its schema. The chain verification (`read_evidence`). The rule that only `kind: verdict`
and `by: judge` records are kept. The Map view.

## Done when

`scripts/test.sh plugins/substrate/tests/test_morphogen.py` passes; `scripts/verdicts.sh` re-reads the existing
log and verdict 3's item is unchanged in its old fields; `scripts/check.sh` passes.
