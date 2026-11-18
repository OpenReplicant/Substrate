# Task 4: the rename pass

**Model:** Sonnet. **Needs:** nothing; do it on its own commit so it is easy to review. Read the glossary in
`docs/tasks/README.md` first.

## Scope

Change the **words people read**, not the names programs use. No behaviour changes: every test suite passes
before and after with no test edited except for a message it asserts on.

**Change** (prose and labels): `README.md`, `CLAUDE.md`, `workbench/BRIEF.md`, `plugins/*/README.md`,
`plugins/substrate/MAP.md`, `docs/direction.md`, `docs/multi-process.md`, `docs/assistant/`, the skills in
`.claude/skills/`, comments and docstrings, what scripts print, labels and headings in the shell's pages,
descriptions in content types and in `streams.yaml`.

**Keep** (identifiers; each renamed later, when the thing it names moves or is rebuilt):

| Kept | Why |
| --- | --- |
| paths, module and file names (`workbench/`, `ladder.py`, `vocabulary.yaml`, `vocab.py`, `scripts/workbench.sh`) | the glossary: code paths change when Workbench moves to the kernel repository |
| database names: schemas, tables, columns, roles, functions (`wb.*`, `api.decide`) | a migration, not a rename |
| extractor, plugin, stream and handler ids (`substrate:drift`, `drift-gaps`, `review-lane`), decision kinds, relation names, `x-term` values and the `sub:` terms | they are stored in claims and decisions already made; renaming them orphans history |
| MCP tool names, HTTP routes, env settings (`WB_*`, `WORKBENCH_*`), container and volume names | interfaces other things call |
| `DECISIONS.md` and `docs/spec.md` | the first is append-only; the second is the record and has its own task (`spec-rewrite.md`) |
| everything under `repos/` | Morphogen keeps "cell"; it changes by its own pull requests |
| `docs/contracts/`, `docs/tasks/` | already in the new words |

## The glossary, with the judgement calls made

| Today | Becomes | Note |
| --- | --- | --- |
| Workbench, kernel (as the product) | Knowledge Kernel | first use in a file: "the Knowledge Kernel (`workbench/`)". "The old kernel repository" stays as it is |
| the ladder, the handlers ladder | the fallback learner | a stream's ordered handlers stay "route"; "rank" stays |
| vocabulary | **ontology** where it means classes and properties (everything Workbench and the plugins have today); **taxonomy** only for a scheme of concepts with broader and narrower. None exists yet, so expect no use of "taxonomy" except in forward-looking prose |
| term | class or property (in an ontology) | "term" in its everyday sense stays |
| review lane | moderation queue | |
| approval policy | workflow | see `docs/contracts/workflow.md` |
| cell | governed component | only where Substrate speaks for itself; "cell" stays wherever the text is about Morphogen's file or fields |
| "model" for the map | map | "model" meaning a language model stays |
| drift (the noun for a difference) | gap | the extractor is still named `substrate:drift`; write "the drift extractor finds gaps" |

When a sentence is unclear about which sense it means, leave it and add it to a list in the commit message.

## Files to touch

About 120 tracked files mention Workbench, 30 "vocabulary", 30 "drift", 27 "review lane", 20 "ladder" (counts
outside `repos/`, `DECISIONS.md` and `docs/spec.md`). Work file by file, not by blind substitution: `git grep
-il "review lane"` and so on, and read each hit.

## Leave alone

The Keep table. The map's items in the Knowledge Kernel (their descriptions change with their source files on
the next extract; do not `save_item` to reword them). `catalog-info.yaml` is never hand-edited: if a
description on the map changed, `scripts/map.sh export` regenerates it.

## Done when

- `scripts/test.sh` passes (all suites), and `scripts/check.sh` passes;
- `git grep -il "review lane\|handlers ladder\|approval policy"` outside the kept files returns nothing;
- `git diff --stat` shows no file renamed and no `.sql` file changed;
- the commit message lists the sentences left for a person to decide.
