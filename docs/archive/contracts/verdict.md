# Contract: the verdict

Between **Morphogen** (which writes it) and **Substrate** (which reads it into the Knowledge Kernel and acts on
it). A verdict is the only thing that lets a change to a governed component be proposed for landing.

Read from Morphogen at `52385af`: `morphogen/schema.py` (`evidence-record/v1`, published as
`schemas/evidence-record.v1.json`), `evidence.py`, `judge.py`; and `plugins/substrate/substrate_plugin.py`
(extractor `morphogen`), `plugins/substrate/types/verdict.json`.

## The record

One row of Morphogen's evidence log: `<git common dir>/morphogen/evidence.db`, SQLite, append-only (update and
delete abort), hash-chained (`hash = sha256(canonical record)`, `prev` the one before, `seq` from 1).

| Field | Meaning |
| --- | --- |
| `seq`, `hash`, `prev`, `at` | the record's place in the chain; `(seq, hash)` is its identity everywhere |
| `kind` | `verdict`. A `probe` or a `measurement` is practice, never a verdict |
| `by`, `trust` | `judge`, and `measured` (or `simulated` for a simulated interface) |
| `verdict` | `pass` or `fail`. "Refused" is a fail, in words |
| `claim` | `<cell>: <candidate> is better than | not better than <base>` |
| `cell`, `subject`, `scope` | what was judged |
| `refs.base`, `refs.candidate` | full commit ids |
| `outcome.metrics.<metric>` | `base` and `candidate` medians, `gain` (relative, or absolute when the cell says), `ci95` (bootstrap of paired gains), `sign_test_p` (one-sided, ties dropped), `runs`, `tied`, `ok`, `primary` |
| `outcome.*` otherwise | why a change was refused before or beside the measure: `forbidden`, `denied`, `parameter_violations`, `check`, `interfaces`, `system`, `wrong`, `failed` |
| `gate.decision` | `merge`, `review` or `none` (`workflow.md`). The judge never merges |
| `served`, `settings`, `request`, `seeds`, `labels` | what the run was given (names and digests, never values), the request's digest, the caller's labels. `labels` never decide |

A pass needs the primary metric's gain at or over its `min` (default 0.05) with `sign_test_p` at or under 0.01,
no other metric regressing past its `max_regression`, every test passing and nothing forbidden touched. Rounds
are paired and alternate order; close calls get more rounds up to `max_repeats`.

## What Substrate may do with it

1. **Read, verify, copy.** `scripts/verdicts.sh` re-verifies the whole chain and keeps only records with
   `kind: verdict` and `by: judge`. A broken chain keeps nothing. Each becomes a `verdict` item whose every
   value cites `morphogen:evidence.db#<seq>`, related `judges` to its component.
2. **Never write one.** No script, handler, extractor or person in Substrate appends to the evidence log or
   saves a `verdict` item by another path. A volunteer's result, a probe, a screen, a trial in `docs/choices`
   and a model's opinion are claims, not verdicts.
3. **A fail is kept.** A refused change stays in the Knowledge Kernel as a negative result with what was tried;
   the cheat log (direction step 5) is built from these.
4. **A pass is necessary, not sufficient.** What happens next is the workflow's (`workflow.md`). An approval
   cites the verdict by `seq` and `hash`, and is void if `refs.candidate` is not the commit being landed.
5. **Compare only like with like.** Two verdicts are comparable when `cell`, `refs.base`, `served.gateway.meter`
   and the inputs digest agree. A changed scorer, case set or meter starts a new series.

## What Substrate reads today, and what it will need

Read now: `claim`, `verdict`, `gate.decision`, `cell`, `refs`, `trust`, `outcome.metrics` (whole), `seq`,
`hash`, and of `outcome` the keys `forbidden`, `denied`, `check`, `interfaces`, `wrong`, `failed`.

Not read, and needed by the experiments in this order:

| Field | Needed by | Why |
| --- | --- | --- |
| `labels` | step 3 | to name the experiment a verdict belongs to (same-candidate, worse-candidate, compile-down) without parsing the claim |
| `outcome.parameter_violations`, `outcome.system` | step 5 | two of the ways a cheat is refused; the cheat log would miss them |
| `inputs` digest, `served.gateway.meter` | step 4 | rule 5's comparability |
| `gate.owner`, `gate.lifecycle` | `workflow.md` | who may approve |

Each is an additive change to `verdict.json` and the extractor, made in the task that needs it.

## The two checks that the judge can see (direction step 3)

Morphogen has no same-candidate check in code; its `CLAUDE.md` asks for one by hand after a change to the
statistics (0 of 12 passed on 2026-11-05). On Substrate's side it is a procedure with a fixed reading:

- **Same against same:** a candidate commit whose governed files equal the base's (an empty commit, or a
  comment-only change in `change`). Expected: `verdict: fail`, with no primary metric `ok`. One pass in the
  series is a finding about the environment (its noise, its case count), reported before any real comparison.
- **Worse against base:** a candidate made worse on purpose in a known way (answers dropped, a smaller model
  named). Expected: `verdict: fail`, the outcome metric's `ci95` wholly below zero. If the judge cannot refuse
  it, the environment has too few cases or too much noise to carry step 4, and that is fixed first.

Both are ordinary verdicts in the log, labelled, and kept.

## Open

- A held-out budget (how many verdicts a held-out set has been used for) is not in the record. Substrate can
  count verdicts per inputs digest once it reads the digest; the rule for retiring a set is the owner's.
- Cost has no field of its own: it is a `metered.*` metric. Dollars per run would be a third metric from the
  same meter, added when a paid model is in a comparison.
