# Packages

A package is one environment and an agent configured for it, in a directory of its own: what is started and
shared (`docs/contracts/environment.md`, S-102). Installing one is copying its directory here and naming it in
`PACKAGES` in `.env`; `scripts/up.sh` then loads its content types and declares it to the handlers plugin, and a
saved item of the type its environment starts from begins an episode. No script per package.

| Package | Environment | Agent | Judged by |
| --- | --- | --- | --- |
| `lookups` | a question about a software package, answered from a registry (PyPI, npm, crates.io, GitHub, Hugging Face): search, fetch, answer, hand off | one model handler, Granite 4.0 Micro through the gateway (held fixed) | `scored.correct`: answers equal to the registry field at a recorded date; floors 0 (hands off) and 0.208 (always "yes") on `dev` |
| `papers` | one paper's abstract (arXiv id, title, abstract); the one action is `record`, gated by cited sentences (`environment.yaml`) | one model handler, named in `agent.yaml` (default `ollama/granite4:3b`, the one `lookups` uses), through the gateway; `per_call` abstracts to a call | `scored.correct` on `dev`: the mean of four per-field agreements; floors 0 (hands off) and 0.2438 (always other / none); the harvest by `tests/test_papers.py` on recorded pages |

## lookups

- **Ask:** save a `question` item (the shell, or MCP `save_item` with `type: question`, `fields: {question: ...}`),
  then run `handlers:run` (MCP `run_extractor`, or `scripts/streams.sh run`). The answer, or the hand-off, is on
  the input `lookups-<slug>`: `final`, and `episode` (each step's claims and action, and every page read, kept
  whole). A hand-off waits in the review lane. Every model call is a `call` item, metered at the gateway.
- **Files:** `environment.yaml` (sensors, actions and gates, the view a fetch is shown in, the model, the
  outcome and its floors), `environment.py` (reset, step, encoders, the recording fetch), `agent.yaml`,
  `handlers/` (the model handler and its instructions), `notes/`, `driver.py` and `score.py` (the judged run),
  `cases/` (`dev.jsonl` and `dev.outcomes.jsonl`, and `dev.fetched.jsonl.gz`, the record a dev run replays),
  `plugin/` (the `question` type), `tests/`.
- **Dev run, no network:** `python3 packages/lookups/driver.py --cases packages/lookups/cases/dev.jsonl |
  python3 packages/lookups/score.py --outcomes packages/lookups/cases/dev.outcomes.jsonl` (the gateway at
  `MORPHOGEN_GATEWAY`, a key in `WB_GATEWAY_KEY`).
- **Held-out cases** are the operator's, outside the repository: `cases.jsonl` and `fetched.jsonl.gz` (recorded
  once with `driver.py --cases FILE --record FILE --network`) in Morphogen's inputs, `outcomes.jsonl` in its
  private directory. The cell is `component:lookups` in `morphogen.yaml`.
- **Contract test:** `scripts/contract.sh environment lookups` (dev cases, no model, no network).

## papers

The paper catalog (`docs/archive/tasks/paper-catalog.md`) and the pipeline from a need to a judged result
(`docs/archive/tasks/rd-pipeline.md`): what has been published about agent harnesses and cognitive designs with language models, as
data. The harvest is plain code with no model; reading each abstract into a fixed record is the package's agent, and the
lookup over the records is plain code again.

- **Start it:** put `papers` in `PACKAGES` in `.env` and run `scripts/up.sh` (it loads the plugin's types and links
  `plugins/papers` to `packages/papers/plugin`, where the server and the shell look). A package with only a `plugin/`
  and no `environment.yaml` is loaded the same way; nothing is declared to the handlers.
- **Run it:** `scripts/workbench.sh extract papers:harvest` (or `papers:listings`, `papers:metadata`,
  `papers:testable` one at a time). It prints what it wrote and what the catalog holds; a second run over unchanged
  sources writes nothing and says so. Inputs, `--input KEY=VALUE`: `batches` (arXiv requests of 100 papers, default 80),
  `checks` (GitHub repositories read per run, default 100, or what GitHub's rate limit allows), `max_age_hours` (a
  page read less long ago is not read again, default 1), `replay` (a directory of recorded fetches: no network).
- **Sources:** `listings.yaml`: the 20 curated lists of `sources.survey.yaml` (their READMEs) and three saved arXiv
  searches for cognitive architectures with language models (300 results each). From a list only the arXiv
  identifiers in links, the heading each sat under and its line are taken: its descriptions are not copied. arXiv
  metadata is CC0; its terms are kept (one request every three seconds, one connection, the client name
  `paper-catalog/0.1`). GitHub is read without a login (60 requests an hour) unless `WB_PAPERS_GITHUB_TOKEN` is in the
  extractor's environment. Not used: Semantic Scholar's API, OpenAlex, Hugging Face's papers API, OpenReview, full text.
- **Items:** `listing` (a list or a saved search: licence as GitHub reports it, last change, stars, papers resolved,
  links without an arXiv identifier, machine-built) and `paper` (arXiv's metadata, `listed_in`: each list that names
  it with its heading, line and the link found, and a `listedIn` relation to the listing with the same quote; the
  repositories named in its abstract or comment; `testable` and `testable_why`). Every value is a claim quoting the
  Atom element, JSON key or link it came from, with that URL as its source.
- **Testable, by rule:** a repository, a licence GitHub reports as MIT, Apache-2.0, BSD-*, ISC, LGPL-*, CC0-1.0,
  Unlicense or MPL-2.0, and not archived. Most-listed papers first; it resumes where it stopped.
- **Records:** every fetch is kept under `.state/papers/` (an index of URL, date, hash and status, and each body once),
  so a run can be replayed. `tests/fixtures/` holds small recorded pages.
- **View:** Papers in the sidebar: filters for heading, listing, number of listings, date, repository and testable; a
  row opens to the listings that name it, and Open goes to the item with its claims.
- **Test, no network, no model:** `scripts/test.sh packages/papers/tests/test_papers.py packages/papers/tests/test_reading.py`.

### Reading: the record

- **The environment** (`environment.yaml`, `environment.py`): an input is one paper, its abstract shown in numbered sentences
  (a deterministic splitter: not after e.g., i.e., et al., vs., Fig., Eq., nor inside a decimal or version). The one action is
  `record` with the fields `component_kind` (14 values), `slot` (handler, route, notes, sensor, learner, outcome, none), `does`,
  `result`, `needs`, each with a `<field>_sentences`: one to three sentence numbers. A small model cannot copy a quote word for
  word, so it points and the environment copies. The gate is code: the numbers must exist in that paper and be at most three, or
  the field is refused and stays empty; a value outside the lists is refused; `other` and `none` claim nothing and need no
  sentences; a `quote` the model sends is ignored. The stored quote is the cited sentences' text.
  Hand-off is allowed. `agent.yaml` names the model (through the gateway, caller `handler:papers-main`), the handler is
  `handlers/model.py`, and `reading.py` is how a paper is shown and a reply read, shared with the record pass.
- **`per_call`** (`agent.yaml`, parameters, default 1): abstracts shown in one call, each under its arXiv id, the answer one record
  per id (`record_batch`). The gate is applied to each paper in its own abstract: a sentence number the paper does not have is refused, an id not in
  the batch is ignored, a paper the answer skipped is unread and asked again in a later call. The step loop carries one input an
  episode, so the driver and the record pass make the batch themselves (`handlers/` and `plugins/handlers/` are as they were).
- **Dev cases:** `cases/dev.jsonl` (40 abstracts, chosen across the catalog's headings; arXiv metadata is CC0) and
  `cases/dev.outcomes.jsonl`. **The reference records were written by a model (Claude Sonnet 5.5, reading each abstract), not by a
  person, and are open for a person to correct**; each reference was first written as quotes, then converted to the sentences that hold them, and passes the same gate (`tests/test_reading.py`). Held-out
  cases are the operator's, as for `lookups`.
- **Dev run:** `python3 packages/papers/driver.py --cases packages/papers/cases/dev.jsonl [--per_call N] |
  python3 packages/papers/score.py --outcomes packages/papers/cases/dev.outcomes.jsonl` (the gateway at `MORPHOGEN_GATEWAY`, a
  key in `WB_GATEWAY_KEY`). `scored.correct` is the mean over cases of four agreements (kind equal, slot equal, `result` cites a sentence the
  reference's `result` also cites, `needs` the same; both empty agrees); `does` is not scored. The scorer replays each line's
  actions through the environment, never reading its `final`, and prints `floor_nothing`, `floor_empty` and `floor_constant`.
- **Contract test:** `scripts/contract.sh environment papers` (the test reads the environment's `case` and closing action, so it
  also runs for an environment with no fetch).
- **Record pass:** `scripts/workbench.sh extract papers:records --input limit=25` (MCP `run_extractor`): testable papers first,
  most-listed first, `limit` papers a run (default 20), `per_call`, `model`, `pace` (seconds between calls). A paper already read
  with the same model and instructions (`record_hash`) is skipped, so a run resumes. Each accepted field is written onto the
  `paper` as a claim whose quote is the cited sentences' text and whose author is `model:MODEL`; `record_by` says which model and when.
  A 429 waits 30, 60 and 120 s, then the run stops and the next resumes.
- **Lookup:** `scripts/workbench.sh run packages/papers/lookup.py "a need in words" [--kind K] [--slot S] [--testable yes]
  [--limit 5] [--json]`: Workbench's recall limited to papers (`workbench recall --type paper`, MCP `search` with `types`,
  the server's `POST /wb/api/recall`), then each paper's kind, slot, testable, listing count and citations. It needs vectors made
  (`scripts/recall.sh`); without them it ranks by words and the graph only.
- **Queue:** `trial` (queued, running, replicated, not replicated, dropped) and `trial_why` on `paper`; who set them is the claim's
  author. The Papers view filters on kind, slot and trial, searches by need (the lookup), and queues or drops a paper with a reason.
