# Task: the `papers` package: read, then reproduce

**Model:** Opus to build each stage; the largest for the reproducing stage's design and its judge checks.
**Needs:** `first-package.md` (S-102, S-103: tools are actions, the agent starts as one model handler, the
directory is `packages/papers/`, and it reuses the step loop built for `lookups`); stage 1 of `starter-agent.md` is done (Granite 4.0 Micro, the tool loop,
S-100). This is the starter agent's research stream made specific (S-101) and direction step 7 brought forward.

## Stage A: reading

- **Stream `papers-reading`**: an input is a paper (an arXiv id, a URL or a file someone saved). A source for
  new papers on agent architectures (a registry query) can come later; first the owner saves them.
- **Tools**: fetch that records (URL, date, body hash, body, kept for replay), text from the PDF or HTML page,
  recall, record. Look up the current docs of whatever does the PDF text before choosing it (`research` skill).
- **Objects**: `paper` (title, authors, date, source, licence), and its **stated claims**: what the paper says
  it does and found (method, components, datasets, baselines, reported numbers), each a claim attributed to the
  authors, quoting the paper with its place in the text. Code links become catalog candidates.
- **Outcome** (a script, no model's opinion), two numbers, because the first alone gives full marks to an
  agent that quotes the title (S-103): **grounded**, the share of quotes found in the recorded text; and
  **covered**, the share of a paper's main stated claims (a list a person wrote, held with the outcomes, never
  shown to the agent) that a recorded claim matches. Covered decides; grounded may not fall. Plus what the
  person did with the reading (accepted, edited, redone).
- **Cases**: `dev` papers in the repository's cases file by id only; held-out papers chosen by the operator.
- **Governed components**: the reading prompt, the tool descriptions, the notes, the hand-up rule.

Done when: five papers the owner picked are in the Knowledge Kernel with their claims, every claim opens to
its quote, and the grounded score is printed per paper.

## Stage B: reproducing

- **Stream `papers-reproducing`**: an input is a read paper whose method fits a slot Substrate has (how a
  handler is prompted, what it is shown, how it hands up, what is compiled down).
- **Action**: write the method as a candidate component or plugin on a branch, against the slot's contract
  test, then ask for a judged run against the baseline at equal budget on an environment's held-out cases.
  The gate is `propose`: nothing lands without the workflow (`docs/contracts/workflow.md`).
- **Outcome**: Morphogen's verdict. The store keeps both: the authors' reported claim and what was measured
  here, as replicated or not, each negative with its source (S-91's rule for negatives).
- **The loop this opens**: a method that passes becomes part of the agent that reads the next paper. Each turn
  of it is an ordinary judged change; the judge and the cases stay out of every candidate's reach.

Done when: one paper's method has been written as a candidate, screened on its contract test and `dev` cases,
judged once, and recorded as replicated or not, with the same-against-same and worse-candidate checks
(`docs/contracts/verdict.md`) run first on the environment it was judged on.

## Leave alone

`repos/morphogen` (changes go upstream). Held-out cases. Papers' text is kept only where its licence allows;
otherwise keep quotes and the URL. No second model: one cheap model held fixed (S-97).
