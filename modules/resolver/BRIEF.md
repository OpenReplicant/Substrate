# resolver: one entity resolution, built once

**For:** kernel's milestone 6 plans entity resolution (M6-T9: names, roles and mentions of the same thing
linked, `skos:exactMatch` when certain, `skos:closeMatch` for review, Splink plus embeddings). Morphogen's
`demos/entity-resolution` already judges a resolver against held-out pairs (F1 0.422 to 0.428 so far).
These are one job (S-07).

## Shape

- **The module** lives in kernel's `modules/` (by pull request there), as M6-T9 specifies: a processor that
  reads entities under its own role and submits match claims with their score and method.
- **Its cells** are Morphogen's: `matcher`, `blocking`, `backend` (Splink or the demo's own), threshold.
  `morphogen.yaml` in the module's directory names them; held-out pairs stay outside the repository.
- **Every merge is reversible:** a match is a claim, and a wrong one is refuted, never undone by deleting.

## Tests first

M6-T9's own check: fixture people and organisations resolve as expected; an injected contradiction becomes
a question and nothing is deleted. Plus Morphogen's: a verdict on the module's matcher cell, in Podman.

## Until it lands

The substrate uses the demo through Morphogen and records its verdicts with `encoder-morphogen`.
