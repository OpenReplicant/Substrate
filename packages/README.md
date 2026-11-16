# Packages

A package is one environment and an agent configured for it, in a directory of its own: what is started and
shared (`docs/contracts/environment.md`, S-102). Installing one is copying its directory here and naming it in
`PACKAGES` in `.env`; `scripts/up.sh` then loads its content types and declares it to the handlers plugin, and a
saved item of the type its environment starts from begins an episode. No script per package.

| Package | Environment | Agent | Judged by |
| --- | --- | --- | --- |
| `lookups` | a question about a software package, answered from a registry (PyPI, npm, crates.io, GitHub, Hugging Face): search, fetch, answer, hand off | one model handler, Granite 4.0 Micro through the gateway (held fixed) | `scored.correct`: answers equal to the registry field at a recorded date; floors 0 (hands off) and 0.208 (always "yes") on `dev` |
| `papers` | none in leg one (no `environment.yaml`): the sources are listed in `listings.yaml` | none in leg one: plain code, no model | `tests/test_papers.py` on recorded pages; the run's own counts |

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

Leg one of the paper catalog (`docs/tasks/paper-catalog.md`): what has been published about agent harnesses and
cognitive designs with language models, as data. No model is used; the harvest is plain code.

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
- **Test, no network:** `scripts/test.sh packages/papers/tests/test_papers.py`.
