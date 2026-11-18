# Substrate

**The primitives for emergence, as a coding and devops tool.** Point Substrate at a repository and it works on
it the way an active developer would: it maps what is there, builds toward what should be, reconciles what is
left, and hands every change to a gate it cannot get around. Point it at itself and it is self-modifying; that is
a choice of target, not a different design.

| Part | Where | Does |
| --- | --- | --- |
| **Mapper** | `.claude/skills/map`, `catalog`, `research` | sources into maps with evidence: parts, the roles they play, the interfaces that make them interchangeable, goals; and catalogs of alternatives for each role |
| **Builder** | `.claude/skills/build` | closes the gap from the blueprint to what is, by pull request |
| **Reconciler** | `.claude/skills/reconcile` | compares the maps and the record, and writes the gaps that remain |
| **Judge**, outside | [Morphogen](https://github.com/OpenReplicant/Morphogen) | decides whether a change is really better, on cases the builder cannot reach |

**Maps are files.** Backstage descriptor files, one entity per file under `map/`, in three namespaces: what should
be (`blueprint`), what people say (`described`), what is (`observed`). Every claim points at the lines of the file
it rests on, with their hash; `python3 check.py` says when a source has changed under a claim. Substrate's map of
itself is `catalog-info.yaml`.

**The gate is the target's, never the asker's.** Whoever asks for a change, a person or an agent, says what they
want and how they would know; how that is measured and who may merge come from the target's base branch.

The design is [`docs/seed.md`](docs/seed.md), the plan [`docs/plan.md`](docs/plan.md), every decision and its
reason [`DECISIONS.md`](DECISIONS.md). The first target is [MetaSoar](https://github.com/OpenReplicant/MetaSoar):
the original Soar cognitive architecture, with Substrate on its impasses.

## Use

Open the repository in Claude Code; the skills load from `.claude/skills`. Then:

```sh
python3 check.py            # the map is well formed and its evidence current
python3 check.py --stamp    # after writing new evidence
```

Needs git, python3 and Claude Code. The framework this tree was built for (a store on Postgres, a real-time
environment, a companion with a voice and a face, a local model) is kept at the tag `framework-final`.

## Licence

Apache License 2.0 (`LICENSE`).
