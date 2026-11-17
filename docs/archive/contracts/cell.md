# Contract: the cell (a governed component)

Between **Substrate** (which names what may change) and **Morphogen** (which judges a change to it). Substrate
says "governed component"; Morphogen says "cell". They are the same thing seen from two sides. The Knowledge
Kernel is not a party: Morphogen never reads it, and reads the map only from `catalog-info.yaml` at the base
commit.

Read from Morphogen at `52385af` (#80): `morphogen/project.py` (`CellDoc`, `ProjectDoc`), `backstage.py`,
`documents.py`, `BRIEF.md` ("Morphogen in one page").

## What a cell is

Five fields, all read from the **base** commit, never from the candidate:

| Field | Says | Substrate's rule |
| --- | --- | --- |
| `change` | the only files or settings a candidate may touch (`path`, a glob, `path#NAME`, `path:dotted.key`, with `in lo..hi` or `in [a, b]` on a setting) | as narrow as the hypothesis: one file where one will do |
| `run` | the workload, run in `dir` | an environment's driver (`environment.md`); never part of `change` |
| `better` | metrics and directions; the first is primary unless one says `primary: true` | one cost metric and one outcome metric, below |
| `tests` | what must keep passing; a failure refuses, it is never traded for score | the component's own tests and its interfaces' tests |
| `in` | the cell or system it belongs to (scope and the system guard) | from the map's `partOf`, never written by hand |

Optional, and used here: `score` (a scorer from the base, run outside the candidate), `dir`, `rounds`
(`warmup`, `repeats`, `max_repeats`), `timeout`, `keep` (settings a candidate may not change), `owner` and
`lifecycle` (`workflow.md`). The rest of `CellDoc` (`observe`, `same_as_base`, `same_output`, `provides`,
`consumes`, `guard`, `simulates`, `requires`, `description`) is Morphogen's to document. Unknown keys are an
error (`extra="forbid"`), so this contract adds no key to the cell.

## Where each part is written

| What | Where | Who writes it |
| --- | --- | --- |
| that the component exists, what it is part of, its owner and lifecycle | its `component` item in the Knowledge Kernel, exported by `scripts/map.sh export` to `catalog-info.yaml` | the map (rule 8) |
| `change`, `run`, `score`, `better`, `tests`, `rounds`, `timeout` | `morphogen.yaml` under `cells:`, keyed `component:<slug>`; or `morphogen.dev/<field>` annotations in the export | a commit on the trunk, reviewed like any change to the judge's rules |
| held-out answers (`private`), the search set (`search`), the cases without answers (`inputs`), the gateway and its meter, served env and services, budget | `morphogen.local.yaml` on the operator's machine, under `cells: {<slug>: ...}`; never committed | the operator |

A field given in both the catalog and `morphogen.yaml` must agree, or `structure check` reports `conflict`.

## Rules both sides hold

1. **A candidate cannot change its own rules.** `morphogen.yaml`, `morphogen.local.yaml`, the scorer, the
   driver and the cases are outside every `change`. A hypothesis that needs the workload changed is two changes:
   the workload first, by people, then the candidate.
2. **Held-out paths are outside the repository** and reach only the scorer, as `MORPHOGEN_PRIVATE`. The run
   gets `MORPHOGEN_INPUTS` (cases with no outcome). Nothing derived from `private` is written into the Knowledge
   Kernel, a prompt, a knowledge file or another environment's cases.
3. **`better` is two metrics, never a ratio.** Value per dollar is judged as an outcome metric and a cost
   metric, each with its own bound, so a cheaper answer cannot buy a worse one:
   - cost: `metered.<name>` (calls or tokens counted by the operator's meter at the gateway), or a metric the
     judge itself measures (`wall_seconds`, `cpu_seconds`, `max_rss_kb`);
   - outcome: `scored.<name>`, printed by the scorer;
   - a cost hypothesis is `metered.x: {lower: true, min: m}` with `scored.y: {higher: true, gain: absolute,
     max_regression: 0}`; a quality hypothesis swaps which is primary and holds cost with `max_regression`.
   A metric the candidate reports about itself (`reported.*`) never decides.
   **Money is one cost among several, and often zero** (free and local models). The meter reports every
   factor the gateway's own record has, as counts, for every run: `calls`, `answered`, `tokens_in`,
   `tokens_out`, `tokens_cached` (input tokens read from a cache), `seconds` and `seconds_upstream` (latency
   with and without the gateway's overhead), `retries`, `cost`. Morphogen takes any numeric key the meter
   returns as `metered.<key>`; a cell's `better` names the ones that decide or bound, and the rest are
   recorded. Ratios (cache hit = `tokens_cached / tokens_in`, tokens per second) are computed when read, from
   the counts, never stored as a metric. Latency on a shared GPU is noisy: bound it, do not make it primary,
   until a same-against-same series shows it is stable.
4. **One name.** The map's slug, the cell's key (`component:<slug>`) and the verdict's `cell` name the same
   thing, so a verdict finds its component without a lookup table.
5. **A cell is added when a hypothesis needs it** (direction, backlog rule). Today there is one:
   `component:model-handler`. Next, by S-94: the router, then recall's weights.

## Check

`bin/morphogen structure check morphogen.yaml` reports no error. It checks the format, containment and
interfaces. It does not check that `run`, `score` or the held-out paths exist: the first judged run does.

## Open

- Morphogen's compiled cell has a `modality`, but `morphogen.yaml` cannot set it, so the selector cannot narrow
  by it yet. Upstream, when a second optimizer is tried.
- `morphogen.local.yaml` keys the cell `model-handler` while `morphogen.yaml` keys it `component:model-handler`.
  It works (evidence 3 was scored), but the spelling rule is Morphogen's and should be stated there.
