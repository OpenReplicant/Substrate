# Task: ready for someone else to pick up, and for a first client system

**Model:** Opus for the three walks; the largest model reads the findings and cuts the follow-up briefs.
**Needs:** the owner for walk 2 (about twenty minutes, and which system). **First in the order now** (S-97).

## Scope

Find out what stops (a) a newcomer from running Substrate from a fresh clone, and (b) the owner from taking on
a client's system: mapping it, finding its gaps, and judging one improvement to it. Substrate has only ever
modelled itself; `CLAUDE.md` says nothing built here may work only on itself, and that has not been tested.

Three walks. Each is done as the person would do it, reading only what they would read, and every place it
breaks, misleads or needs knowledge that is not written down is a finding. **Fix nothing during a walk** except
a typo or a wrong path; a finding becomes a brief.

1. **The newcomer's walk.** From `README.md`, then `CLAUDE.md` and the `setup` skill, check every command,
   path, port and file they name against the repository. Then list what is true only on this machine:
   absolute paths under a home directory in tracked files, the GPU compose file, models assumed pulled, settings
   `.env.example` lacks, steps that need the owner's accounts. Do not bring up a second stack beside the running
   one; if a real fresh-clone run is wanted, say what it needs (another machine, or the stack stopped) and
   leave it to the owner.
2. **The second system's walk.** With the owner, through the `interview` skill, map one system that is not
   Substrate, in its own domain: recommend this machine (`scripts/observe.sh` already reads it), unless the
   owner names a client-like one. Stop at a map with its parts, their purposes in the owner's words, and the
   gaps the drift extractor finds. Record: every place a script, view, extractor or message assumes the system
   is Substrate; whether the Map view, `scripts/trace.sh` and recall work on the new domain; whether anything
   of it leaked into this repository (`git status` must stay clean of it).
3. **The optimization walk, on paper.** For one part of that system that should improve, write what "better"
   means, its cell (`docs/contracts/cell.md`) and where its cases would come from. Then trace, without running
   a judged run, what Substrate's tooling assumes: where `morphogen.yaml` and the evidence log live for a
   system in another repository, whether `scripts/verdicts.sh` can read that log, whether the gateway's meter
   can count that system's model calls. Each "it cannot" is a finding.

## Files to touch

- `docs/readiness.md` (new): the findings, each with where it was hit, who it blocks (newcomer, client, both)
  and how bad (stops them, slows them, cosmetic), most severe first.
- `.state/interviews/<system>/` and the new domain in the Knowledge Kernel (walk 2), which stay out of git.
- `observe.local.yaml` (gitignored), only with what the owner allows.

## Leave alone

Code, scripts and skills (findings only). `catalog-info.yaml`: another system's map is never exported here.
`repos/`. The owner's files beyond what they name in the interview. No judged run, no benchmark, no new part.
What a client is offered and at what price is the owner's (positioning); record questions, not answers.

## Done when

`docs/readiness.md` lists the findings from all three walks; the second system's map is in the Knowledge
Kernel with the owner's claims behind it and `git status` shows none of it; `scripts/check.sh` passes (it checks
only Substrate's own domain, so the second system's map is shown by `scripts/trace.sh` on one of its parts); the
largest model has turned the findings that stop someone into briefs in this folder, in order.
