# Packages

A package is one environment and an agent configured for it, in a directory of its own: what is started and
shared (`docs/contracts/environment.md`, S-102). Installing one is copying its directory here and naming it in
`PACKAGES` in `.env`; `scripts/up.sh` then loads its content types and declares it to the handlers plugin, and a
saved item of the type its environment starts from begins an episode. No script per package.

| Package | Environment | Agent | Judged by |
| --- | --- | --- | --- |
| `lookups` | a question about a software package, answered from a registry (PyPI, npm, crates.io, GitHub, Hugging Face): search, fetch, answer, hand off | one model handler, Granite 4.0 Micro through the gateway (held fixed) | `scored.correct`: answers equal to the registry field at a recorded date; floors 0 (hands off) and 0.208 (always "yes") on `dev` |

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
