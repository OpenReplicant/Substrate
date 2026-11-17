# Task: the meter reports every cost factor

**Model:** Opus (it is the judge's side; small, but a wrong count misleads every later verdict).
**Needs:** nothing. **Before:** task 6's first judged run, so the new series starts clean. S-96;
`docs/contracts/cell.md` rule 3.

## Scope

`scripts/gateway.py judge-meter close` returns `calls`, `answered`, `tokens`, `tokens_in`, `tokens_out`,
`cost`. Add, from columns Bifrost's `logs` table already has: `tokens_cached` (`cached_read_tokens`),
`seconds` (`latency`), `seconds_upstream` (`upstream_latency`), `retries` (`number_of_retries`). Sums over the
same rows the existing query counts, nulls as zero. Keep every existing key and its meaning.

Find out and write down (in the docstring and in the `DECISIONS.md` row):

1. the unit of `latency` and `upstream_latency` (check Bifrost's docs for the pinned version; convert to
   seconds if it is not);
2. whether `cached_read_tokens` is ever non-zero for the models in use (Ollama, OpenRouter's free models). If
   never, keep the key and say so;
3. whether a `metered.<key>` that a cell's `better` does not name appears in the verdict record or only in the
   run's samples (read `repos/morphogen/morphogen/judge.py`; do not change it). If it is dropped, the fix is
   Morphogen's: write it up for the `upstream` skill.

## Files to touch

`scripts/gateway.py` (`judge_meter`), its test if one exists (add one against a fake `logs` table if not),
`plugins/handlers/README.md` only if it describes the meter's keys, `DECISIONS.md` (one row).

## Leave alone

`repos/morphogen`. The handlers' own meter (`meter`, per call id): it serves live streams and is not the
judge's. `morphogen.yaml`: no cell's `better` changes here. The marker-call logic that closes the window.

## Done when

`judge-meter open` then `close` around a handful of real calls through the gateway prints the new keys with
plausible values (tokens in and out equal the old total; seconds close to the wall time of the calls);
`scripts/test.sh` and `scripts/check.sh` pass. Not done in the same commit as any governed component.
