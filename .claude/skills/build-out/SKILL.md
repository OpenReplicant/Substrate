---
name: build-out
description: Build substrate toward its spec (docs/spec.md) one step of docs/build.yaml at a time - brief, build, check, record - stopping at decisions that are the owner's. Use when the SessionStart hook says the spec is in place, when the owner says "continue", "build it out" or "next step", or after the setup skill passes.
---

# Build out the spec

`docs/spec.md` is what substrate is meant to become; `docs/build.yaml` is its build plan with each step's status.
While both are in place, sessions here work through the plan. If the owner asks for something else, do that
instead; this skill is the default, not an override.

## Each session

1. **Where it stands.** `python3 scripts/spec.py status`, then `python3 scripts/spec.py next` for the step to
   work on (a step marked `doing` comes first; otherwise the first `todo` whose `after` steps are done).
   Read the spec sections it names, and any brief in its folder.
2. **The stack runs first.** If it is not up (`scripts/check.sh` fails), use the setup skill first; nothing
   else is built on a stack that does not run.
3. **Say what you are about to do**, in a line, and set the step to `doing`
   (`python3 scripts/spec.py set ID doing`).
4. **Brief first.** For a new module, write or update `modules/<name>/BRIEF.md` before code: what it reads, what
   it writes (claims through change sets only, kernel's module contract), its role, its check. The repository's
   rules apply throughout (CLAUDE.md): look things up and pin them, core first, one tested path, licences, the
   map.
5. **Build where the work belongs.** Glue and substrate modules here; anything in kernel or Morphogen upstream
   by pull request (the upstream skill), following that repository's own CLAUDE.md.
6. **Judge what claims to improve something.** A change that is meant to make something better (recall
   quality, a skill, a threshold) lands only with a Morphogen verdict; a change that only adds a part needs its
   check to pass.
7. **Check, then record.** Run the step's `check`. Only when it passes: `python3 scripts/spec.py set ID done`,
   update `catalog-info.yaml` if a part was added (and `bin/morphogen structure check morphogen.yaml`), add a
   `DECISIONS.md` row for any default chosen, run `scripts/check.sh`, and commit with the step in the message
   ("spec step 1: ...").
8. **One step per session**, unless a step is small and the owner is watching and wants the next. Stop with a
   short note: what was done, the check's result, what is next.

## When a step cannot go on

- **The owner's decision** (`needs_owner: true`, or anything CLAUDE.md says is theirs: kernel changes, licences,
  positioning, money): prepare the case (a brief, a draft branch, the evidence, a recommendation), ask the
  owner in one question, and set the step `blocked` with `--waiting-on "owner: <the question>"` if they are
  not there to answer. Then go on to the next step that does not depend on it.
- **Something outside** (an upstream PR under review, a tool that does not run on this machine): set it
  `blocked` with what it waits on, and move on.
- **A verdict against it**: set it `dropped` and say why in the step's notes; a dropped step is a result, not a
  failure.

## Changing the plan

The plan can be wrong. When a step turns out to need splitting, reordering or a different check, propose the
change to the owner with the reason, and edit both `docs/spec.md` and `docs/build.yaml` once they agree. Never
mark a step done by weakening its check.
