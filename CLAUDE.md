# Substrate

The seed (S-155, S-162): a mapper, a builder and a reconciler, as skills, working on files, with Morphogen as
the judge outside. Its spec is `docs/seed.md`; what is built next is `docs/plan.md`; every default and its reason
is in `DECISIONS.md` (append-only). Read the plan first.

| Part | Where |
| --- | --- |
| The skills | `.claude/skills/`: `map`, `catalog`, `research`, `build`, `reconcile` |
| The map of itself | `catalog-info.yaml` and `map/` (namespaces `blueprint`, `described`, `observed`) |
| The check | `check.py` (standard library only) |

The framework before S-162 (store, environment, companion, voice head, local model, components, UI, gateway
config, trials) is at the tag `framework-final`; take a part back only when a target needs it.

## Rules

1. **Look it up, then pin it.** Read a tool's current docs before relying on it; pin exact versions; prefer
   releases at least two weeks old; record what you pinned and where you read it.
2. **Choose from catalogs, not memory**: the `research` skill, for any component, library, service or model.
3. **Every claim in the map carries evidence**, and every change ends with `python3 check.py` passing, or the
   failure named and explained.
4. **Done is the gate's verdict, not your report.** Changes go by branch and pull request; never change a target's
   gate policy, its judge's settings or cases in the same change as the work they judge.
5. **Morphogen is the judge, from GitHub** (S-156): install and call it from `OpenReplicant/Morphogen`, never from
   a local clone (`repos/morphogen` stays untouched): a judge run from a clone would be the candidate.
6. **Secrets never enter a committed file, a log, a commit message or chat.**
7. **Licences:** permissive or LGPL for what a repository contains; check before adding.
8. **Nothing installed on the host** beyond git, python3 (standard library), a container engine and Claude Code.

## Working with the owner

- Recommend one option and keep moving; ask only for decisions that are theirs (positioning, licences, privacy,
  spending money, what to build next). Say what you recommend when you ask.
- Plain words; describe the loop plainly rather than reaching for broad framings.
- Decisions go in `DECISIONS.md` as new rows (append-only; supersede, never edit a committed row).
- Use the smallest model that can do a subtask (subagents on Haiku unless judgment is needed).
